"""Read-only gate audit; write results only under the gitignored outputs folder."""
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from markdown_it import MarkdownIt

from src.common import fingerprint
from src.extraction import PII, clean
from src.pipeline_a_course_ingestion import aspect_card
from src.pipeline_b_indsf_skills import verify_benchmark

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
COURSES = ["SAIA1013", "SAIA2113", "SAIA2143"]
SKILLS = [f"S{n:02d}" for n in range(1, 13)]
gates = []


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def record(number, title, checks, details):
    gates.append({"gate": number, "title": title,
                  "status": "PASS" if all(checks.values()) else "FAIL",
                  "checks": checks, "details": details})


expected_files = ["course_catalog_manifest.json", "parsed_course_chunks.json",
                  "verbatim_lookup_store.json", "indsf_all_extracted_skills.json",
                  "industry_skills_benchmark.json", "ingestion_quality_report.md",
                  "indsf_quality_report.md", "retrieval_smoke_test_report.md"]
file_checks = {}
for name in expected_files:
    path = OUT / name
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        file_checks[name] = bool(json.loads(text))
    else:
        tokens = MarkdownIt().parse(text)
        file_checks[name] = bool(tokens) and tokens[0].type == "heading_open" and "\x00" not in text

chunks = read("parsed_course_chunks.json")
catalog = read("course_catalog_manifest.json")["courses"]
lookup = read("verbatim_lookup_store.json")
items = read("indsf_all_extracted_skills.json")
skills = read("industry_skills_benchmark.json")
indexed = [c for c in chunks if c.get("indexable")]
schema_errors = []
for c in indexed:
    valid = all(isinstance(c.get(k), str) and c[k].strip()
                for k in ["chunk_id", "doc_id", "verbatim_text_span"])
    valid = valid and c.get("course_code") in COURSES and c.get("evidence_level") in ["CLO", "Taught", "Assessed"]
    valid = valid and type(c.get("pdf_page_no")) is int and c["pdf_page_no"] >= 1
    if not valid:
        schema_errors.append(c.get("chunk_id"))
record(1, "Output Artifacts & Schema Integrity", {**file_checks, "indexable_chunk_schema": not schema_errors,
       "unique_chunk_ids": len({c["chunk_id"] for c in chunks}) == len(chunks)},
       {"files": len(file_checks), "parsed_pages": len(chunks), "indexable_chunks": len(indexed), "schema_errors": schema_errors})

index = read("indexes/manifest.json")
index_chunks = read("indexes/chunks.json")
index_ids = {c["chunk_id"] for c in index_chunks}
checks, ci_details = {}, {}
phrases = {"SAIA1013": ["Recommend resolutions", "Explain methodologies", "Practise the appropriate ethical risk"],
           "SAIA2143": ["Explain the concepts and process", "Construct data transformation", "Demonstrate presentation skills"]}
for code in ["SAIA1013", "SAIA2143"]:
    ci = [c for c in chunks if c["course_code"] == code and c["evidence_level"] == "CLO"]
    text = " ".join(c["verbatim_text_span"] for c in ci if c["chunk_id"] in index_ids)
    checks[code + "_forced_ocr_and_tables"] = bool(ci) and all(
        c["ocr_forced"] and c["ocr_status"] == "completed" and not c["ocr_native_word_masking"]
        and c["table_extraction_status"] == "completed" and c["ocr_extracted_text"] and c["tables_markdown"] for c in ci)
    checks[code + "_indexed_clo_statements"] = all(f"CLO{n}" in text for n in [1, 2, 3]) and all(p in text for p in phrases[code])
    ci_details[code] = {"ci_pages": len(ci), "auxiliary_clo_pages": len(catalog[code]["auxiliary_clo_pages"])}
course = catalog["SAIA2113"]
ci_dirs = list((ROOT / "data/courses").glob("SAIA2113*/01_CI_CLO"))
checks["SAIA2113_empty_ci_folder"] = bool(ci_dirs) and all(not any(p.iterdir()) for p in ci_dirs)
checks["SAIA2113_deterministic_abstention"] = (course["level_availability"]["CLO"] is False
    and course["level_status"]["CLO"] == "folder_empty_or_missing"
    and not course["auxiliary_clo_pages"] and not index["partitions"]["routed"]["SAIA2113::CLO"])
ci_details["SAIA2113"] = {"availability": course["level_availability"]["CLO"], "status": course["level_status"]["CLO"]}
record(2, "CI/CLO OCR & Extraction", checks, ci_details)

checks, deck_details = {}, {}
for code in COURSES:
    cards = catalog[code]["deck_aspect_cards"]
    ready = [d for d in catalog[code]["documents"] if d["evidence_level"] == "Taught" and d["status"] == "ready"]
    checks[code + "_all_ready_decks_have_cards"] = {c["doc_id"] for c in cards} == {d["doc_id"] for d in ready}
    matches = []
    for card in cards:
        pages = [c for c in chunks if c["course_code"] == code and c["doc_id"] == card["doc_id"]]
        matches.append(aspect_card(card["doc_id"], pages) == card)
    checks[code + "_scanner_matches_saved_cards"] = all(matches)
    deck_details[code] = {"nonempty": sum(bool(c["declared_learning_outcomes_or_agenda"]) for c in cards),
                          "total": len(cards), "empty_decks": [c["doc_id"] for c in cards if not c["declared_learning_outcomes_or_agenda"]]}
record(3, "Deck Aspect Card Coverage", checks, deck_details)

pii_counts = {}
for name in ["parsed_course_chunks.json", "verbatim_lookup_store.json"]:
    text = (OUT / name).read_text(encoding="utf-8")
    pii_counts[name] = {kind: len(pattern.findall(text)) for kind, pattern in PII.items() if kind in ["email", "phone"]}
parity_errors = [c["chunk_id"] for c in indexed if not c["verbatim_text_span"] or c["verbatim_text_span"] not in
                 lookup.get(f"{c['course_code']}::{c['doc_id']}::{c['pdf_page_no']}", "")]
hotel = next(c for c in chunks if c["course_code"] == "SAIA2113" and c["doc_id"] == "Week 1 - INTRODUCTION TO ML.pdf" and c["pdf_page_no"] == 15)
offices = [c for c in chunks if c["course_code"] == "SAIA1013" and c["doc_id"] == "Week 1 Introduction to RAI and AI Ethics Class Notes.pdf" and c["pdf_page_no"] in [1, 4]]
record(4, "PII Redaction & Verbatim Parity", {
    "zero_detectable_email_and_mobile": all(n == 0 for counts in pii_counts.values() for n in counts.values()),
    "hotel_room_preserved": bool(re.search(r"1\s*room", hotel["verbatim_text_span"], re.I)) and not any(e["kind"] == "office_room" for e in hotel["redaction_events"]),
    "utm_offices_redacted": len(offices) == 2 and all("[REDACTED_PII]" in c["verbatim_text_span"] and "060601" not in c["verbatim_text_span"] and any(e["kind"] == "office_room" for e in c["redaction_events"]) for c in offices),
    "cleaner_regression": clean("1 room", boilerplate=False) == ("1 room", []) and clean("MJIIT 060601", boilerplate=False)[0] == "[REDACTED_PII]",
    "all_indexable_substrings": not parity_errors},
    {"pii_match_counts": pii_counts, "substring_matches": len(indexed) - len(parity_errors), "indexable_chunks": len(indexed), "parity_errors": parity_errors,
     "hotel_office_redactions": sum(e["kind"] == "office_room" for e in hotel["redaction_events"]), "utm_office_pages": [c["pdf_page_no"] for c in offices]})

by_id = {i["item_id"]: i for i in items}
refs = [r for s in skills for r in s["indsf_provenance"]]
verify_benchmark(skills, read("indsf_raw_extracted.json"), items)
special = {s["skill_id"]: [{"section_type": r["section_type"], "item_id": r["item_id"], "excerpt": r["matched_source_excerpt"]} for r in s["indsf_provenance"]] for s in skills if s["skill_id"] in ["S03", "S08"]}
record(5, "Pipeline B Provenance", {
    "all_12_skills": sorted(s["skill_id"] for s in skills) == SKILLS,
    "query_and_nli_present": all(all(s.get(k, "").strip() for k in ["retrieval_query", "nli_hypothesis_template"]) for s in skills),
    "three_provenance_items_each": all(len(s["indsf_provenance"]) == 3 for s in skills),
    "all_references_exist": all(r["item_id"] in by_id for r in refs),
    "all_excerpts_equal_full_b1_records": all(r["matched_source_excerpt"] == by_id[r["item_id"]]["verbatim_text"] for r in refs),
    "S03_S08_substantive_sections": all(any(r["section_type"] in ["job_description_tasks", "competencies"] for r in rows) for rows in special.values()),
    "pipeline_b_source_verifier": True},
    {"extracted_items": len(items), "skills": len(skills), "references": len(refs), "S03_S08": special})

log = read("retrieval_smoke_test_log.json")
report = (OUT / "retrieval_smoke_test_report.md").read_text(encoding="utf-8")
sections = re.findall(r"^## (SAIA\d+) / (S\d+):[^\n]*\n(.*?)(?=^## |\Z)", report, re.M | re.S)
expected_pairs = {(c, s) for c in COURSES for s in SKILLS}
times = [float(re.search(r"Retrieval time: ([\d.]+) ms", body)[1]) for _, _, body in sections]
weights = []
for directory, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in [".git", ".venv", "__pycache__"] and not d.startswith("verification-")]
    for name in files:
        path = Path(directory) / name
        if path.suffix.lower() in [".safetensors", ".pt", ".pth", ".onnx", ".gguf", ".ckpt", ".bin"]:
            weights.append(path.relative_to(ROOT).as_posix())
probes = [".venv/Scripts/python.exe", "src/__pycache__/probe.pyc", ".pytest_cache/probe", *weights]
ignored = subprocess.run(["git", "check-ignore", "-z", "--stdin"], input=("\0".join(probes) + "\0").encode(), capture_output=True, check=True).stdout.decode().split("\0")
tracked = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode().split("\0")
tracked_cache = [p for p in tracked if p and ("__pycache__/" in p or p.startswith((".venv/", "outputs/models/")) or Path(p).suffix in [".pyc", ".safetensors", ".pt", ".pth", ".onnx", ".gguf", ".ckpt"])]
status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True)
checks = {"report_all_36_pairs": len(sections) == 36 and {(c, s) for c, s, _ in sections} == expected_pairs,
          "log_all_36_pairs": len(log["queries"]) == 36 and {(q["course_code"], q["skill_id"]) for q in log["queries"]} == expected_pairs,
          "latency_under_3000_ms": all(0 <= t < 3000 and math.isfinite(t) for t in times) and all(0 <= q["elapsed_ms"] < 3000 for q in log["queries"]),
          "report_log_latency_agreement": all(abs(times[i] - log["queries"][i]["elapsed_ms"]) <= .051 for i in range(len(times))),
          "benchmark_fingerprint_current": log["benchmark_fingerprint"] == fingerprint(skills),
          "index_source_fingerprint_current": log["index_source_fingerprint"] == index["source_fingerprint"] == fingerprint({"chunks": chunks, "catalog": read("course_catalog_manifest.json")}),
          "cache_and_existing_weights_ignored": all(p in ignored for p in probes), "no_tracked_cache_or_weights": not tracked_cache,
          "SAIA2113_missing_clo_abstains": all(not q["routed"]["CLO"]["hits"] and q["routed"]["CLO"]["status"] == "INSUFFICIENT_EVIDENCE (Folder Empty)" for q in log["queries"] if q["course_code"] == "SAIA2113")}
record(6, "Retrieval Smoke Test & Repo Hygiene", checks,
       {"queries": len(sections), "latency_min_ms": min(q["elapsed_ms"] for q in log["queries"]), "latency_max_ms": max(q["elapsed_ms"] for q in log["queries"]),
        "latency_scope": "pooled plus available routed searches, excludes model loading", "current_benchmark_fingerprint": fingerprint(skills), "logged_benchmark_fingerprint": log["benchmark_fingerprint"],
        "ignored_weight_files": weights, "tracked_cache_or_weights": tracked_cache, "git_status": status.stdout.splitlines(), "git_status_stderr": status.stderr,
        "gitignore_is_untracked": "?? .gitignore" in status.stdout})

result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "overall": "PASS" if all(g["status"] == "PASS" for g in gates) else "FAIL", "gates": gates,
          "tests": {"command": ".venv/Scripts/python.exe -m pytest -q --tb=short --basetemp outputs/verification-pytest-final -p no:cacheprovider", "result": "39 passed in 4.27s"},
          "existing_validator": {"command": ".venv/Scripts/python.exe -m src.validate_artifacts", "status": "FAIL", "error": "Retrieval log refers to a different skill benchmark"}}
(OUT / "precommit_gate_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
lines = ["# Precommit gate verification", "", f"Overall: {result['overall']}", "", "| Gate | Status | Failed checks |", "| --- | --- | --- |"]
for g in gates:
    failures = ", ".join(k for k, ok in g["checks"].items() if not ok) or "None"
    lines.append(f"| {g['gate']} - {g['title']} | {g['status']} | {failures} |")
lines += ["", "Tests: 39 passed in 4.27s.", "", "Detailed counts and evidence: precommit_gate_verification.json.", "", "The retrieval log predates the current benchmark fingerprint. Refresh retrieval and rerun validation before committing.", "", "No pipeline source or existing corpus/report files were changed by this audit."]
(OUT / "precommit_gate_verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
for g in gates:
    print(f"Gate {g['gate']}: {g['status']} - {g['title']}")
    for key, ok in g["checks"].items():
        if not ok:
            print(f"  FAIL: {key}")
print("Reports: outputs/precommit_gate_verification.json and .md")
