"""Blind human check of every Supported claim, for the citation faithfulness rate (CFR).

Two commands:
  sheet  collect every Supported claim of configurations B, B+V, P and P+V from a saved
         run into one CSV. Identical claims appear once. The sheet hides NLI scores,
         verifier results and which configuration made each claim; rows are in a fixed
         shuffled order. citation_check_key.json records which configurations made
         each claim and is not meant to be opened while checking.
  score  read the filled-in sheet and the key; report per configuration the CFR
         (claims a person confirmed / claims made), the unsupported-claim rate (UCR),
         claims whose quote is not on the cited page, and the share of Supported cells
         that carry a quote, document and page.

A claim is confirmed only when the cited page contains the quote AND the quote
supports the skill at that level. No model is loaded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from src.common import ROOT, md, read_json, write_json
from src.evaluate_ground_truth import file_sha256
from src.run_skill_audit_pipeline import version_text

DEFAULT_RESULTS = ROOT / "outputs" / "reference_run_2026-11-19_22659c7" / "skill_coverage_audit_results.json"
DEFAULT_DIR = ROOT / "outputs" / "citation_check"
CONFIGURATIONS = ("B", "B+V", "P", "P+V")
ANSWERS = ("page_contains_quote", "supports_skill_at_level")
COLUMNS = ("claim_id", "course_code", "skill_id", "skill_name", "skill_description", "level", "source_file",
           "page_or_slide", "quote", "what_the_level_requires", *ANSWERS, "note")
LEVEL_REQUIREMENT = {
    "CLO": "An official course learning outcome or course synopsis statement in the Course Information document",
    "Taught": "Material that teaches a concept, method or technique of the skill, not a passing mention",
    "Assessed": "An assignment task, examination question or rubric criterion that requires the skill",
}


def claim_of(cell: dict, configuration: str) -> dict | None:
    """The (document, page, quote) a configuration cites for a cell, or None if it made no Supported claim."""
    routed, baseline, audit = cell["routed"], cell["baseline"], cell["baseline_audit"]
    if configuration == "B" and baseline["final_classification"] == "Supported":
        source = baseline["draft"]
    elif configuration == "B+V" and audit["final_classification"] == "Supported":
        source = audit["verified_citation"]
    elif configuration == "P" and (routed.get("draft") or {}).get("draft_classification") == "Supported":
        source = routed["draft"]
    elif configuration == "P+V" and routed["final_classification"] == "Supported":
        source = routed["verified_citation"]
    else:
        return None
    return {"doc_id": source.get("doc_id"), "page": source.get("pdf_page_no"), "quote": source.get("verbatim_quote") or ""}


def claim_key(cell: dict, claim: dict) -> str:
    quote = " ".join(claim["quote"].lower().split())
    return "|".join(map(str, (cell["course_code"], cell["skill_id"], cell["level"], claim["doc_id"], claim["page"], quote)))


def source_files(catalog: dict | None) -> dict:
    if not catalog:
        return {}
    return {(course, d["doc_id"]): d.get("source_relative_path", d["doc_id"])
            for course, info in catalog["courses"].items() for d in info["documents"]}


def build_sheet(results: dict, catalog: dict | None) -> tuple[list[dict], dict]:
    skills = {s["skill_id"]: s for s in results["skills"]}
    files = source_files(catalog)
    claims = {}
    for cell in results["cells"]:
        for configuration in CONFIGURATIONS:
            claim = claim_of(cell, configuration)
            if claim is None:
                continue
            key = claim_key(cell, claim)
            entry = claims.setdefault(key, {"cell": cell, "claim": claim, "configurations": []})
            entry["configurations"].append(configuration)
    # Fixed shuffle: order by a hash of the claim, so neither configuration nor course order shows.
    ordered = sorted(claims.items(), key=lambda item: hashlib.sha256(item[0].encode()).hexdigest())
    rows, key_file = [], {}
    for number, (key, entry) in enumerate(ordered, start=1):
        cell, claim, claim_id = entry["cell"], entry["claim"], f"C{number:03d}"
        skill = skills[cell["skill_id"]]
        rows.append({"claim_id": claim_id, "course_code": cell["course_code"], "skill_id": cell["skill_id"],
                     "skill_name": skill["skill_name"], "skill_description": skill["retrieval_query"], "level": cell["level"],
                     "source_file": files.get((cell["course_code"], claim["doc_id"]), claim["doc_id"]),
                     "page_or_slide": claim["page"], "quote": claim["quote"],
                     "what_the_level_requires": LEVEL_REQUIREMENT[cell["level"]],
                     "page_contains_quote": "", "supports_skill_at_level": "", "note": ""})
        key_file[claim_id] = {"configurations": entry["configurations"], "claim_key": key}
    return rows, key_file


def write_sheet(results_path: Path, catalog_path: Path, out_dir: Path) -> int:
    sheet, key = out_dir / "citation_check_sheet.csv", out_dir / "citation_check_key.json"
    for path in (sheet, key):
        if path.exists():
            raise FileExistsError(f"{path} already exists; it may contain your answers, so it is not overwritten")
    results = read_json(results_path)
    rows, key_file = build_sheet(results, read_json(catalog_path) if catalog_path.is_file() else None)
    out_dir.mkdir(parents=True, exist_ok=True)
    with sheet.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    write_json(key, {"schema_version": 1, "results_path": str(results_path), "results_sha256": file_sha256(results_path),
                     "claims": key_file})
    return len(rows)


def yes_no(value: str) -> bool | None:
    folded = (value or "").strip().lower()
    return True if folded in ("yes", "y") else False if folded in ("no", "n") else None


def presence(results: dict) -> dict:
    """Automatic check: every Supported cell carries a quote, a document and a page."""
    report = {}
    for configuration in CONFIGURATIONS:
        claims = [claim_of(c, configuration) for c in results["cells"]]
        claims = [c for c in claims if c is not None]
        complete = sum(bool(c["quote"].strip()) and bool(c["doc_id"]) and isinstance(c["page"], int) for c in claims)
        report[configuration] = {"supported_cells": len(claims), "with_quote_document_page": complete}
    return report


def score_sheet(sheet_path: Path, key_path: Path, results_path: Path) -> dict:
    key = read_json(key_path)
    if file_sha256(results_path) != key["results_sha256"]:
        raise ValueError("The results file differs from the one the sheet was made from")
    with sheet_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = {r["claim_id"]: r for r in csv.DictReader(handle)}
    problems = [f"{cid}: missing from the sheet" for cid in key["claims"] if cid not in rows]
    problems += [f"{cid}: not in the key" for cid in rows if cid not in key["claims"]]
    answers = {}
    for cid, row in rows.items():
        values = [yes_no(row.get(a, "")) for a in ANSWERS]
        if None in values:
            problems.append(f"{cid}: answer both {' and '.join(ANSWERS)} with yes or no")
        answers[cid] = values
    if problems:
        shown = problems[:20] + ([f"... and {len(problems) - 20} more"] if len(problems) > 20 else [])
        raise ValueError("Citation check sheet has problems:\n  " + "\n  ".join(shown))
    results = read_json(results_path)
    scores = {}
    for configuration in CONFIGURATIONS:
        ids = [cid for cid, entry in key["claims"].items() if configuration in entry["configurations"]]
        confirmed = sum(all(answers[cid]) for cid in ids)
        scores[configuration] = {"claims": len(ids), "confirmed": confirmed,
                                 "quote_not_on_page": sum(not answers[cid][0] for cid in ids),
                                 "cfr": confirmed / len(ids) if ids else None,
                                 "ucr": (len(ids) - confirmed) / len(ids) if ids else None}
    return {"schema_version": 1, "scores": scores, "presence": presence(results),
            "inputs": {"sheet_path": str(sheet_path), "sheet_sha256": file_sha256(sheet_path),
                       "results_path": str(results_path), "results_sha256": key["results_sha256"],
                       "code_version": results.get("code_version"),
                       "hardware": results.get("hardware", {}).get("device", "not recorded")}}


def render(report: dict) -> str:
    def pct(value):
        return "n/a" if value is None else f"{value:.1%}"
    lines = ["# Citation check", "",
             "A person opened each cited page without seeing NLI scores, verifier results or which configuration made the "
             "claim. A claim is confirmed when the page contains the quote and the quote supports the skill at that level. "
             "CFR = confirmed / claims; UCR = 1 - CFR.", "",
             "| Configuration | Claims | Confirmed | CFR | UCR | Quote not on the cited page |", "| --- | --- | --- | --- | --- | --- |"]
    for name, s in report["scores"].items():
        lines.append(f"| {name} | {s['claims']} | {s['confirmed']} | {pct(s['cfr'])} | {pct(s['ucr'])} | {s['quote_not_on_page']} |")
    lines += ["", "Citation and span presence (automatic): Supported cells carrying a quote, document and page.", "",
              "| Configuration | Supported cells | With quote, document and page |", "| --- | --- | --- |"]
    for name, p in report["presence"].items():
        lines.append(f"| {name} | {p['supported_cells']} | {p['with_quote_document_page']} |")
    ident = report["inputs"]
    lines += ["", "## Inputs", "", f"- Results: `{md(ident['results_path'])}` (SHA-256 `{ident['results_sha256'][:16]}`)",
              f"- Sheet: `{md(ident['sheet_path'])}` (SHA-256 `{ident['sheet_sha256'][:16]}`)",
              f"- Code that produced the run: {md(version_text(ident['code_version']))}", f"- GPU: {md(ident['hardware'])}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("sheet", "score"):
        command = commands.add_parser(name)
        command.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
        command.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Folder for the sheet, key and scores")
        if name == "sheet":
            command.add_argument("--catalog", type=Path, default=ROOT / "outputs" / "course_catalog_manifest.json")
    args = parser.parse_args()
    try:
        if args.command == "sheet":
            count = write_sheet(args.results, args.catalog, args.dir)
            print(f"Wrote {count} claims to {args.dir / 'citation_check_sheet.csv'}")
        else:
            report = score_sheet(args.dir / "citation_check_sheet.csv", args.dir / "citation_check_key.json", args.results)
            write_json(args.dir / "citation_check_scores.json", report)
            (args.dir / "citation_check_scores.md").write_text(render(report), encoding="utf-8")
            print(render(report).split("\n## Inputs")[0])
    except (FileExistsError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
