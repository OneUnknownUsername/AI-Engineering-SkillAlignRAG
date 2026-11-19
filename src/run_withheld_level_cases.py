"""Withhold one evidence level of one course and check that the audit abstains.

Each case copies the course files to a work folder, then either deletes one level's
folder ("missing") or replaces its files with one unreadable file ("unprocessable").
It re-runs ingestion and indexing on the copy, audits that course's skills (routed
and pooled baseline) and records, for the withheld cells:

- routed: Insufficient Evidence with the matching reason and no model call
- baseline: whether it labelled the cell anything other than Insufficient Evidence
- routed cells of the course's other levels: unchanged from the reference run

data/courses and the main outputs are never modified. Results go to
outputs/withheld_level_runs/ (summary.md, summary.json, one JSON per case). A case
whose JSON already exists is skipped, so an interrupted run can be resumed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from src.common import COURSES, LEVELS, ROOT, code_version, md, read_json, write_json

INSUFFICIENT = "Insufficient Evidence"
LEVEL_FOLDERS = {level: folder for folder, level in LEVELS.items()}
MODES = {"missing": ("folder_empty_or_missing", "folder is empty or missing"),
         "unprocessable": ("processing_failed", "could not be processed")}
COPIED_OUTPUTS = ("normalized_pdf", "extraction_cache")  # Small caches the case may update.
LINKED_OUTPUTS = ("models", "tools")  # Read-only: the embedding model and LibreOffice.
DEFAULT_REFERENCE = ROOT / "outputs" / "reference_run_2026-11-19_22659c7" / "skill_coverage_audit_results.json"


def default_cases(availability: dict) -> list[tuple[str, str, str]]:
    """Every available level withheld as missing; every level of the last complete course as unprocessable."""
    cases = [(c, l, "missing") for c in COURSES for l in LEVELS.values() if availability[c][l]]
    complete = [c for c in COURSES if all(availability[c].values())]
    if complete:
        cases += [(complete[-1], l, "unprocessable") for l in LEVELS.values()]
    return cases


def case_name(course: str, level: str, mode: str) -> str:
    return f"{course}_{level}_{mode}"


def prepare_case(data_dir: Path, source_outputs: Path, work: Path, course: str, level: str, mode: str) -> tuple[Path, Path]:
    """Build the work copy with one level withheld; return its data and output folders."""
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}")
    if work.exists():
        shutil.rmtree(work)
    data, outputs = work / "data", work / "outputs"
    shutil.copytree(data_dir / "courses", data / "courses")
    folders = [p for p in (data / "courses").glob(course + "*") if p.is_dir()]
    if len(folders) != 1:
        raise ValueError(f"Expected one course folder for {course}, found {len(folders)}")
    level_folder = folders[0] / LEVEL_FOLDERS[level]
    if level_folder.exists():
        shutil.rmtree(level_folder)
    if mode == "unprocessable":
        level_folder.mkdir(parents=True)
        (level_folder / "withheld_unreadable.pdf").write_bytes(
            b"Not a PDF: this file stands in for course documents that cannot be processed.\n")
    outputs.mkdir(parents=True)
    for name in COPIED_OUTPUTS:
        if (source_outputs / name).is_dir():
            shutil.copytree(source_outputs / name, outputs / name, symlinks=True)
    for name in LINKED_OUTPUTS:
        if (source_outputs / name).exists():
            (outputs / name).symlink_to((source_outputs / name).resolve())
    shutil.copy2(source_outputs / "industry_skills_benchmark.json", outputs / "industry_skills_benchmark.json")
    return data, outputs


def routed_view(cell: dict) -> tuple:
    routed = cell["routed"]
    return (routed["final_classification"], (routed.get("draft") or {}).get("draft_classification"),
            (routed.get("verified_citation") or {}).get("verbatim_quote"))


def evaluate_case(course: str, level: str, mode: str, result: dict, reference: dict | None) -> dict:
    expected_status, reason = MODES[mode]
    withheld = [c for c in result["cells"] if c["level"] == level]
    routed_correct = sum(c["routed"]["final_classification"] == INSUFFICIENT and reason in c["routed"].get("abstention_reason", "")
                         and c["routed"].get("llm_called") is False for c in withheld)
    row = {"course": course, "level": level, "mode": mode, "level_status": result["level_status"][level],
           "level_status_correct": result["level_status"][level] == expected_status, "withheld_cells": len(withheld),
           "routed_correct": routed_correct,
           "routed_mislabelled": sum(c["routed"]["final_classification"] != INSUFFICIENT for c in withheld),
           "baseline_mislabelled": sum(c["baseline"]["final_classification"] != INSUFFICIENT for c in withheld),
           "other_cells": None, "other_cells_changed": None}
    if reference:
        ref = {(c["course_code"], c["skill_id"], c["level"]): c for c in reference["cells"]}
        others = [c for c in result["cells"] if c["level"] != level]
        row["other_cells"] = len(others)
        row["other_cells_changed"] = sum(routed_view(c) != routed_view(ref[(c["course_code"], c["skill_id"], c["level"])]) for c in others)
    return row


def natural_rows(reference: dict) -> list[dict]:
    """Levels that are already missing in the reference run count towards the same totals."""
    rows = []
    for course, levels in reference["availability"].items():
        for level, available in levels.items():
            if available:
                continue
            cells = [c for c in reference["cells"] if c["course_code"] == course and c["level"] == level]
            reasons = [c["routed"].get("abstention_reason", "") for c in cells]
            mode = "unprocessable" if any(MODES["unprocessable"][1] in r for r in reasons) else "missing"
            rows.append({**evaluate_case(course, level, mode, {"cells": cells, "level_status": {level: MODES[mode][0]}}, None),
                         "mode": f"{mode} (already in the reference run)", "level_status": "from the reference run",
                         "level_status_correct": None})
    return rows


def run_stage(module_args: list[str], log: Path) -> None:
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n$ python -m {' '.join(module_args)}\n")
        handle.flush()
        result = subprocess.run([sys.executable, "-m", *module_args], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{module_args[0]} failed; see {log}")


def audit_course(output_dir: Path, course: str, result_path: Path, offline: bool) -> None:
    """Worker, run in its own process so GPU memory is released after each case."""
    from src.config import AuditConfig
    from src.run_skill_audit_pipeline import audit_pair, prepare_audit
    ctx, data = prepare_audit(output_dir, AuditConfig(offline=offline))
    cells = []
    for skill in sorted(data["skills"], key=lambda s: s["skill_id"]):
        cells += audit_pair(ctx, course, skill)[0]
    write_json(result_path, {"course": course, "level_status": ctx.catalog["courses"][course]["level_status"],
                             "cells": cells, "code_version": data["code_version"], "hardware": data["hardware"]})


def render(summary: dict) -> str:
    totals = summary["totals"]
    lines = ["# Withheld-level cases", "",
             "Each case withholds one evidence level of one course on a copy of the course files, re-runs ingestion, "
             "indexing and the audit, and checks the withheld cells. Routed is correct when it gives Insufficient Evidence "
             "with the matching reason and without calling the model. The baseline has no Insufficient Evidence outcome.", "",
             "| Course | Level | Withheld as | Level status | Routed correct | Routed mislabelled | Baseline mislabelled | Other routed cells changed |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in summary["rows"]:
        status = r["level_status"] + ("" if r["level_status_correct"] in (None, True) else " (unexpected)")
        changed = "n/a" if r["other_cells"] is None else f"{r['other_cells_changed']}/{r['other_cells']}"
        lines.append(f"| {r['course']} | {r['level']} | {md(r['mode'])} | {md(status)} | {r['routed_correct']}/{r['withheld_cells']} | "
                     f"{r['routed_mislabelled']}/{r['withheld_cells']} | {r['baseline_mislabelled']}/{r['withheld_cells']} | {changed} |")
    lines += ["", f"- Withheld cells: {totals['cells']} across {len(summary['rows'])} levels",
              f"- Routed correct (label, reason, no model call): {totals['routed_correct']}/{totals['cells']}",
              f"- Missing-document conflation rate: routed {totals['routed_mislabelled']}/{totals['cells']} "
              f"({totals['routed_mcr']:.1%}), baseline {totals['baseline_mislabelled']}/{totals['cells']} ({totals['baseline_mcr']:.1%})",
              f"- Routed cells of other levels changed from the reference run: {totals['other_cells_changed']}",
              f"- Code: commit {summary['code_version'].get('commit', 'not recorded')[:12]}"
              + (" with uncommitted changes" if summary['code_version'].get('uncommitted_code_changes') else ""),
              f"- GPU: {md(summary['hardware'])}"]
    return "\n".join(lines) + "\n"


def summarise(rows: list[dict], code: dict, hardware: str) -> dict:
    cells = sum(r["withheld_cells"] for r in rows)
    def total(key):
        return sum(r[key] or 0 for r in rows)
    return {"schema_version": 1, "rows": rows, "code_version": code, "hardware": hardware, "totals": {
        "cells": cells, "routed_correct": total("routed_correct"), "routed_mislabelled": total("routed_mislabelled"),
        "baseline_mislabelled": total("baseline_mislabelled"), "other_cells_changed": total("other_cells_changed"),
        "routed_mcr": total("routed_mislabelled") / cells if cells else 0.0,
        "baseline_mcr": total("baseline_mislabelled") / cells if cells else 0.0}}


def run_cases(args) -> dict:
    catalog = read_json(args.source_outputs / "course_catalog_manifest.json")
    availability = {c: catalog["courses"][c]["level_availability"] for c in COURSES}
    cases = [tuple(c.split(":")) for c in args.case] if args.case else default_cases(availability)
    for course, level, mode in cases:
        if course not in COURSES or level not in LEVELS.values() or mode not in MODES:
            raise ValueError(f"Invalid case {course}:{level}:{mode}")
    reference = read_json(args.reference) if args.reference.is_file() else None
    case_dir = args.output_dir / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    rows, last = [], {}
    for number, (course, level, mode) in enumerate(cases, 1):
        name = case_name(course, level, mode)
        result_path, log = case_dir / f"{name}.json", case_dir / f"{name}.log"
        if not result_path.exists():
            print(f"[{number}/{len(cases)}] {name}", flush=True)
            work = args.work_dir / name
            data, outputs = prepare_case(args.data_dir, args.source_outputs, work, course, level, mode)
            run_stage(["src.pipeline_a_course_ingestion", "--data-dir", str(data), "--output-dir", str(outputs), "--allow-partial"], log)
            run_stage(["src.build_indexes", "--output-dir", str(outputs), "--offline"], log)
            run_stage(["src.run_withheld_level_cases", "audit-course", "--output-dir", str(outputs), "--course", course,
                       "--result", str(result_path)] + (["--offline"] if args.offline else []), log)
            if not args.keep_work:
                shutil.rmtree(work)
        else:
            print(f"[{number}/{len(cases)}] {name}: already done", flush=True)
        last = read_json(result_path)
        rows.append(evaluate_case(course, level, mode, last, reference))
    if reference:
        rows += natural_rows(reference)
    summary = summarise(rows, last.get("code_version", code_version()), last.get("hardware", {}).get("device", "not recorded"))
    write_json(args.output_dir / "summary.json", summary)
    (args.output_dir / "summary.md").write_text(render(summary), encoding="utf-8")
    print(render(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run the withheld-level cases and write the summary")
    run.add_argument("--case", action="append", help="COURSE:LEVEL:MODE, e.g. SAIA2143:Taught:missing (default: all default cases)")
    run.add_argument("--data-dir", type=Path, default=ROOT / "data")
    run.add_argument("--source-outputs", type=Path, default=ROOT / "outputs")
    run.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "withheld_level_runs")
    run.add_argument("--work-dir", type=Path, default=ROOT / "outputs" / "withheld_level_runs" / "work")
    run.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="Run whose other-level results must stay unchanged")
    run.add_argument("--offline", action="store_true", help="Use only cached models")
    run.add_argument("--keep-work", action="store_true", help="Keep each case's work copy for inspection")
    worker = commands.add_parser("audit-course", help=argparse.SUPPRESS)
    worker.add_argument("--output-dir", type=Path, required=True)
    worker.add_argument("--course", required=True)
    worker.add_argument("--result", type=Path, required=True)
    worker.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if args.command == "audit-course":
        audit_course(args.output_dir, args.course, args.result, args.offline)
    else:
        run_cases(args)


if __name__ == "__main__":
    main()
