"""Score a saved audit run against hand-made ground-truth labels.

Two commands:
  template  write a blank CSV to fill in, 108 rows on main (levels with missing documents are
            pre-filled as Insufficient Evidence; the system's answers are not shown)
  score     compare a results file with the filled-in CSV and write
            evaluation_scores.json and evaluation_scores.md

F1 definition (docs/week2_evaluation_criteria.md): each cell is a yes/no question,
"is it Supported?". Every other outcome counts as "no": Not Found, Insufficient
Evidence or a failed model output. Precision, Recall and F1 are computed per level;
Macro-F1 is the average of the per-level F1 scores. No model is loaded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from src.common import COURSES, GENERATION_ERROR, LEVELS, ROOT, load_skill_definitions, md, read_json, write_json
from src.run_skill_audit_pipeline import version_text

LABELS = ("Supported", "Not Found", "Insufficient Evidence")
FAILED = "Failed output"
LEVEL_ORDER = tuple(LEVELS.values())
COLUMNS = ("course_code", "skill_id", "skill_name", "level", "label", "evidence_pages", "note", "lecturer_checked")
CONFIGURATIONS = {
    "B": "Single-pass pooled baseline",
    "B+V": "Baseline with the citation verifier applied afterwards",
    "P": "Source-routed pipeline before the verifier",
    "P+V": "Source-routed pipeline after the verifier",
}
DEFAULT_GROUND_TRUTH = ROOT / "outputs" / "ground_truth" / "ground_truth_levels.csv"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_template(path: Path, catalog: dict, skills: list[dict]) -> int:
    """Write the blank CSV. Never overwrites, because the file may hold annotations."""
    if path.exists():
        raise FileExistsError(f"{path} already exists; it may contain your labels, so it is not overwritten")
    rows = []
    for course in COURSES:
        info = catalog["courses"][course]
        for skill in sorted(skills, key=lambda s: s["skill_id"]):
            for level in LEVEL_ORDER:
                available = info["level_availability"][level]
                note = ""
                if not available:
                    failed = info.get("level_status", {}).get(level) == "processing_failed"
                    note = "Documents could not be processed" if failed else "Documents missing from the course folder"
                rows.append({"course_code": course, "skill_id": skill["skill_id"], "skill_name": skill["skill_name"],
                             "level": level, "label": "" if available else "Insufficient Evidence",
                             "evidence_pages": "", "note": note, "lecturer_checked": "no"})
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel opens the file with the right encoding.
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def canonical_label(value: str) -> str | None:
    folded = " ".join(value.split()).lower()
    return next((label for label in LABELS if label.lower() == folded), None)


def read_ground_truth(path: Path, results: dict) -> tuple[dict, list[str]]:
    """Return {(course, skill, level): row} after strict checks, plus non-blocking warnings."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not UTF-8; in Excel use Save As > 'CSV UTF-8'") from exc
    expected = {(c["course_code"], c["skill_id"], c["level"]) for c in results["cells"]}
    truth, seen, problems = {}, set(), []
    for number, row in enumerate(rows, start=2):  # Row 1 is the header.
        key = tuple((row.get(k) or "").strip() for k in ("course_code", "skill_id", "level"))
        label = canonical_label(row.get("label") or "")
        duplicate = key in seen
        seen.add(key)
        if duplicate:
            problems.append(f"row {number}: duplicate entry for {' / '.join(key)}")
        elif key not in expected:
            problems.append(f"row {number}: {' / '.join(key)} is not a cell in the results file")
        elif label is None:
            problems.append(f"row {number}: label {row.get('label')!r} must be one of {', '.join(LABELS)}")
        else:
            available = results["availability"][key[0]][key[2]]
            if (label == "Insufficient Evidence") == available:
                problems.append(f"row {number}: {' / '.join(key)} is labelled {label}, but the run "
                                f"{'has' if available else 'is missing'} documents for that level")
            truth[key] = {**row, "label": label}
    problems += [f"no row for {' / '.join(k)}" for k in sorted(expected - seen)]
    if problems:
        shown = problems[:20] + ([f"... and {len(problems) - 20} more"] if len(problems) > 20 else [])
        raise ValueError("Ground-truth file has problems:\n  " + "\n  ".join(shown))
    warnings = [f"{' / '.join(k)} is Supported but lists no evidence pages"
                for k, row in sorted(truth.items()) if row["label"] == "Supported" and not (row.get("evidence_pages") or "").strip()]
    return truth, warnings


def predictions(cell: dict) -> dict[str, tuple[str, bool]]:
    """(label, failed) for each configuration. Runs made before the Generation Error label
    stored Not Found for a failed output, so the telemetry flag is checked as well."""
    routed, baseline = cell["routed"], cell["baseline"]
    routed_failed = "generation_error" in routed or routed["final_classification"] == GENERATION_ERROR
    baseline_failed = "generation_error" in baseline or baseline["final_classification"] == GENERATION_ERROR
    draft = routed.get("draft")
    routed_draft = draft["draft_classification"] if draft else routed["final_classification"]
    return {"B": (baseline["final_classification"], baseline_failed),
            "B+V": (cell["baseline_audit"]["final_classification"], baseline_failed),
            "P": (routed_draft, routed_failed),
            "P+V": (routed["final_classification"], routed_failed)}


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score(results: dict, truth: dict) -> dict:
    scores = {}
    for name in CONFIGURATIONS:
        levels, confusion = {}, {}
        for level in LEVEL_ORDER:
            counts = dict.fromkeys(("tp", "fp", "fn", "tn", "failed"), 0)
            table = {gold: dict.fromkeys(LABELS + (FAILED,), 0) for gold in LABELS}
            for cell in (c for c in results["cells"] if c["level"] == level):
                gold = truth[(cell["course_code"], cell["skill_id"], level)]["label"]
                label, failed = predictions(cell)[name]
                if label not in LABELS and not failed:
                    raise ValueError(f"Unknown label {label!r} in results for {name}")
                predicted_yes = label == "Supported" and not failed
                gold_yes = gold == "Supported"
                counts["tp" if gold_yes and predicted_yes else "fn" if gold_yes else "fp" if predicted_yes else "tn"] += 1
                counts["failed"] += failed
                table[gold][FAILED if failed else label] += 1
            tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
            # 2TP/(2TP+FP+FN) equals the harmonic mean; undefined only when no cell is Supported on either side.
            levels[level] = {**counts, "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
                             "f1": ratio(2 * tp, 2 * tp + fp + fn)}
            confusion[level] = table
        defined = [levels[l]["f1"] for l in LEVEL_ORDER if levels[l]["f1"] is not None]
        missing_cells = [c for c in results["cells"] if not results["availability"][c["course_code"]][c["level"]]]
        mislabelled = sum(predictions(c)[name] != ("Insufficient Evidence", False) for c in missing_cells)
        scores[name] = {
            "description": CONFIGURATIONS[name], "levels": levels, "confusion": confusion,
            "macro_f1": sum(defined) / len(defined) if defined else None,
            "levels_without_f1": [l for l in LEVEL_ORDER if levels[l]["f1"] is None],
            "failed_outputs": sum(levels[l]["failed"] for l in LEVEL_ORDER),
            "missing_document_cells": len(missing_cells), "missing_document_mislabelled": mislabelled,
            "missing_document_conflation_rate": ratio(mislabelled, len(missing_cells)),
        }
    base = scores["B"]["macro_f1"]
    for entry in scores.values():
        entry["macro_f1_gain_over_b"] = None if entry["macro_f1"] is None or base is None else entry["macro_f1"] - base
    return scores


def fmt(value: float | None, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}" if percent else f"{value:.3f}"


def render(report: dict) -> str:
    s, ident = report["scores"], report["inputs"]
    lines = ["# Evaluation against ground truth", "",
             "Each cell is scored as a yes/no question: is it Supported? Not Found, Insufficient Evidence "
             "and failed model outputs all count as no. Macro-F1 is the average of the per-level F1 scores; "
             "a level with no Supported cell on either side has no F1 (n/a) and is left out of the average.", "",
             "| Configuration | CLO F1 | Taught F1 | Assessed F1 | Macro-F1 | Gain over B | Failed outputs | Missing-document cells mislabelled |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, e in s.items():
        lines.append(f"| {name} | " + " | ".join(fmt(e["levels"][l]["f1"]) for l in LEVEL_ORDER) +
                     f" | {fmt(e['macro_f1'])} | {fmt(e['macro_f1_gain_over_b'])} | {e['failed_outputs']} | "
                     f"{e['missing_document_mislabelled']}/{e['missing_document_cells']} ({fmt(e['missing_document_conflation_rate'], True)}) |")
    lines += ["", "## Per level", "", "| Configuration | Level | Hits (TP) | False alarms (FP) | Misses (FN) | Precision | Recall | F1 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, e in s.items():
        for level in LEVEL_ORDER:
            v = e["levels"][level]
            lines.append(f"| {name} | {level} | {v['tp']} | {v['fp']} | {v['fn']} | {fmt(v['precision'])} | {fmt(v['recall'])} | {fmt(v['f1'])} |")
    lines += ["", "## Confusion tables", "", "Rows are the ground truth; columns are the configuration's label.", ""]
    for name, e in s.items():
        for level in LEVEL_ORDER:
            lines += [f"**{name}, {level}**", "", "| Ground truth | " + " | ".join(LABELS + (FAILED,)) + " |",
                      "| --- |" + " --- |" * (len(LABELS) + 1)]
            lines += [f"| {gold} | " + " | ".join(str(row[k]) for k in LABELS + (FAILED,)) + " |"
                      for gold, row in e["confusion"][level].items()]
            lines.append("")
    lines += ["## Inputs", "", f"- Results file: `{md(ident['results_path'])}` (SHA-256 `{ident['results_sha256'][:16]}`)",
              f"- Ground truth: `{md(ident['ground_truth_path'])}` (SHA-256 `{ident['ground_truth_sha256'][:16]}`)",
              f"- Lecturer-checked rows: {ident['lecturer_checked_rows']} of {ident['ground_truth_rows']}",
              f"- GPU: {md(ident['hardware'])}", f"- Code that produced the run: {md(version_text(ident['code_version']))}", f"- Benchmark fingerprint: `{ident['benchmark_fingerprint'][:16]}`"]
    if report["warnings"]:
        lines += ["", "## Warnings", ""] + [f"- {md(w)}" for w in report["warnings"]]
    return "\n".join(lines) + "\n"


def run_score(results_path: Path, truth_path: Path, output_dir: Path) -> dict:
    results = read_json(results_path)
    truth, warnings = read_ground_truth(truth_path, results)
    version = results.get("code_version") or {}
    if version.get("uncommitted_code_changes"):
        warnings.insert(0, "The run was produced with uncommitted code changes: " + ", ".join(version["changed_paths"]))
    elif not version:
        warnings.insert(0, "The run predates code-version recording, so its commit is unknown")
    report = {"schema_version": 1, "scores": score(results, truth), "warnings": warnings, "inputs": {
        "results_path": str(results_path), "results_sha256": file_sha256(results_path),
        "ground_truth_path": str(truth_path), "ground_truth_sha256": file_sha256(truth_path),
        "ground_truth_rows": len(truth),
        "lecturer_checked_rows": sum((r.get("lecturer_checked") or "").strip().lower() in ("yes", "y", "true", "1") for r in truth.values()),
        "hardware": results.get("hardware", {}).get("device", "not recorded"),
        "code_version": results.get("code_version"),
        "benchmark_fingerprint": results.get("benchmark_fingerprint", "")}}
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "evaluation_scores.json", report)
    (output_dir / "evaluation_scores.md").write_text(render(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template", help="Write the blank ground-truth CSV")
    template.add_argument("--catalog", type=Path, default=ROOT / "outputs" / "course_catalog_manifest.json")
    template.add_argument("--skills", type=Path, help="Skill file to use instead of the configured skills")
    template.add_argument("--out", type=Path, default=DEFAULT_GROUND_TRUTH)
    scoring = commands.add_parser("score", help="Score a results file against the filled-in CSV")
    scoring.add_argument("--results", type=Path, default=ROOT / "outputs" / "skill_coverage_audit_results.json")
    scoring.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    scoring.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    try:
        if args.command == "template":
            skills = read_json(args.skills) if args.skills else load_skill_definitions()
            count = write_template(args.out, read_json(args.catalog), skills)
            print(f"Wrote {count} rows to {args.out}")
        else:
            report = run_score(args.results, args.ground_truth, args.output_dir)
            print(render(report).split("\n## Per level")[0])
    except (FileExistsError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
