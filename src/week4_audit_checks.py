"""Week 4 data-quality audit checks on the Week 3 course-document output.

Read-only: prints counts and identifiers, never record text, so the output can
be quoted in the public report. Run from the repository root:

    python -m src.week4_audit_checks
"""

import collections
import hashlib
import json
import re
from pathlib import Path

OUTPUT = Path("data/pipeline_v1/course_documents/prepared_text.jsonl")
MANIFEST = Path("data/pipeline_v1/course_documents/pipeline_manifest.json")


def load():
    records = [json.loads(line) for line in OUTPUT.open(encoding="utf-8")]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return records, manifest


def text_key(text):
    return hashlib.sha1(re.sub(r"\s+", " ", text).strip().lower().encode()).hexdigest()


def population(records, manifest):
    print("== Population")
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print("output sha256 matches manifest:", digest in manifest["validation"]["output_sha256"])
    print("records:", len(records), "| indexable:", sum(r["indexable"] for r in records))
    print("sources in manifest:", len(manifest["sources"]))
    cells = collections.Counter((r["course_code"], r["evidence_level"]) for r in records)
    indexable = collections.Counter((r["course_code"], r["evidence_level"]) for r in records if r["indexable"])
    for course, levels in manifest["inspection"]["level_status"].items():
        for level, status in levels.items():
            print(f"  {course} {level}: {cells[(course, level)]} records, "
                  f"{indexable[(course, level)]} indexable, folder {status}")


def raw_hashes(manifest):
    print("== Raw source hashes (local working copy only)")
    missing = mismatched = 0
    for source in manifest["sources"]:
        path = Path(source["path"])
        if not path.exists():
            missing += 1
        elif hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            mismatched += 1
    print("sources:", len(manifest["sources"]), "| missing:", missing, "| hash mismatch:", mismatched)


def uniqueness(records):
    print("== Uniqueness")
    ids = collections.Counter(r["record_id"] for r in records)
    pages = collections.Counter((r["doc_id"], r["page"]) for r in records)
    print("duplicate record_id:", sum(n > 1 for n in ids.values()),
          "| duplicate (doc_id, page):", sum(n > 1 for n in pages.values()))
    groups = collections.defaultdict(list)
    for r in records:
        groups[text_key(r["text"])].append(r)
    repeated = [g for g in groups.values() if len(g) > 1]
    print("exact repeated-text groups:", len(repeated), "| records in them:", sum(map(len, repeated)))
    within = [g for g in repeated if len({r["doc_id"] for r in g}) == 1]
    across = [g for g in repeated if len({r["doc_id"] for r in g}) > 1]
    within_indexable = [r for g in within for r in g if r["indexable"]]
    print("  within one document:", len(within), "groups;", len(within_indexable), "indexable records in",
          len({r["doc_id"] for r in within_indexable}), "documents",
          dict(collections.Counter(r["course_code"] for r in within_indexable)))
    print("  across documents:", len(across), "groups; indexable records in them:",
          sum(r["indexable"] for g in across for r in g))


def consistency(records):
    print("== Consistency: printed_slide_no vs PDF page")
    counts = collections.Counter(
        "none" if r["printed_slide_no"] is None
        else "equal" if str(r["printed_slide_no"]) == str(r["page"]) else "differs"
        for r in records)
    print(dict(counts))
    print("skip reasons:", dict(collections.Counter(r["skip_reason"] for r in records if not r["indexable"])))
    print("extraction methods:", {"+".join(k): v for k, v in
                                  collections.Counter(tuple(r["extraction_methods_used"]) for r in records).items()})


SAMPLE_RULES = [
    ("CLO: SAIA1013 CI with redaction", lambda r: r["course_code"] == "SAIA1013" and r["evidence_level"] == "CLO" and r["redaction_count"] > 0),
    ("CLO: SAIA2143 CI page 2", lambda r: r["course_code"] == "SAIA2143" and r["evidence_level"] == "CLO" and r["page"] == 2),
    ("Assessed: DOCX via converted PDF", lambda r: r["original_format"] == "docx"),
    ("Assessed: SAIA2113 assignment", lambda r: r["course_code"] == "SAIA2113" and r["evidence_level"] == "Assessed"),
    ("Assessed: SAIA2143 exam paper page 2", lambda r: "PMA" in r["doc_id"] and r["page"] == 2),
    ("Taught: PPTX via converted PDF, page 10", lambda r: r["original_format"] == "pptx" and r["page"] == 10),
    ("Taught: OCR-only page", lambda r: r["extraction_methods_used"] == ["rapidocr"]),
    ("Taught: repeated outline page", lambda r: r["doc_id"].startswith("Week 4 - Supervised") and r["page"] == 5),
    ("Taught: page inspected in Week 3", lambda r: r["doc_id"] == "Week 13 Clustering.pdf" and r["page"] == 9),
    ("Taught: long OCR deck, page 50", lambda r: r["doc_id"].startswith("Topic 4- Part 3") and r["page"] == 50),
    ("Taught: short indexable page", lambda r: r["indexable"] and len(r["text"].strip()) < 80),
    ("Skipped: activity_without_explanation", lambda r: r["skip_reason"] == "activity_without_explanation"),
    ("Skipped: divider", lambda r: r["skip_reason"] == "divider"),
    ("Taught: slide tagged auxiliary CLO", lambda r: r["auxiliary_evidence_levels"] == ["CLO"]),
    ("Taught: SAIA2143 page with redaction", lambda r: r["course_code"] == "SAIA2143" and r["evidence_level"] == "Taught" and r["redaction_count"] > 0),
]


def sample(records):
    """Purposive sample: first record in file order matching each rule."""
    print("== Audit sample")
    for number, (reason, rule) in enumerate(SAMPLE_RULES, 1):
        r = next(r for r in records if rule(r))
        print(f"S{number:02d} | {reason} | {r['course_code']} {r['evidence_level']} | {r['doc_id']} p{r['page']}"
              f" | printed {r['printed_slide_no']} | {'+'.join(r['extraction_methods_used'])}"
              f" | indexable {r['indexable']} | chars {len(r['text'])}")


COURSES = {"SAIA1013", "SAIA2113", "SAIA2143"}
LEVELS = ("CLO", "Taught", "Assessed")
LINEAGE = Path("data/week3_manifest.json")


def rule_v1(records, manifest):
    """V1 (FR3, RAI1): every record carries a traceable citation."""
    print("== V1 citation fields (all records)")
    hashes = {s["path"]: s["sha256"] for s in manifest["sources"]}
    pages = {r["source_filename"]: r["pages"] for r in json.loads(LINEAGE.read_text(encoding="utf-8"))["records"]}
    failures = collections.Counter()
    for r in records:
        checks = {
            "doc_id": bool(str(r.get("doc_id") or "").strip()),
            "text": bool(str(r.get("text") or "").strip()),
            "page": isinstance(r.get("page"), int) and 1 <= r["page"] <= pages.get(r["source"], 0),
            "course_code": r.get("course_code") in COURSES,
            "evidence_level": r.get("evidence_level") in LEVELS,
            "source_sha256": r.get("source_sha256") == hashes.get(r["source"]),
        }
        for name, passed in checks.items():
            failures[name] += not passed
        failures["records_failing"] += not all(checks.values())
    print("tested:", len(records), "| passed:", len(records) - failures["records_failing"],
          "| failed:", failures["records_failing"])
    print("failures by condition:", {k: v for k, v in failures.items() if k != "records_failing"})


def rule_v2(records, manifest):
    """V2 (RAI2): each course x level cell has indexable evidence or is a documented gap."""
    print("== V2 category availability (9 course x level cells)")
    indexable = collections.Counter((r["course_code"], r["evidence_level"]) for r in records if r["indexable"])
    gaps = {(g["course_code"], g["evidence_level"]): g["status"] for g in manifest["known_gaps"]}
    result = collections.Counter()
    for course in sorted(COURSES):
        for level in LEVELS:
            n = indexable[(course, level)]
            outcome = "pass" if n else "documented gap (review)" if (course, level) in gaps else "FAIL (undocumented gap)"
            result[outcome] += 1
            if n == 0:
                print(f"  {course} {level}: 0 indexable records -> {outcome}; manifest status: {gaps.get((course, level))}")
    print("result:", dict(result))


MALAY = {"dan", "yang", "untuk", "dengan", "adalah", "kepada", "ini", "tidak", "dalam", "atau", "oleh", "pada",
         "dari", "boleh", "akan", "ialah", "bagi", "secara"}
ENGLISH = {"the", "and", "of", "to", "is", "in", "for", "with", "are", "or", "by", "on", "from", "can", "will",
           "that", "this", "be"}


def coverage(records):
    print("== Coverage: records by level")
    print(dict(collections.Counter(r["evidence_level"] for r in records)))
    print("documents by level:", dict(collections.Counter(
        level for _, level in {(r["doc_id"], r["evidence_level"]) for r in records})))
    print("== Coverage: language (Malay vs English function-word count per record)")
    by_cell, by_doc = collections.Counter(), collections.defaultdict(collections.Counter)
    for r in records:
        words = re.findall(r"[a-z]+", r["text"].lower())
        malay, english = sum(w in MALAY for w in words), sum(w in ENGLISH for w in words)
        language = "malay" if malay > english else "english" if english > malay else "undetermined"
        by_cell[(r["course_code"], r["evidence_level"], language)] += 1
        by_doc[r["doc_id"]][language] += 1
    for key in sorted(by_cell):
        print(" ", *key, by_cell[key])
    for doc, counts in by_doc.items():
        if counts["malay"]:
            print("  Malay-majority document:", doc, dict(counts))
    print("== Pipeline-induced loss: skipped pages by content")
    print(dict(collections.Counter(
        "closing (thank you)" if "THANK YOU" in r["text"].upper() else
        "knowledge check title" if "KNOWLEDGE CHECK" in r["text"] else
        "class activity question" if "CLASS ACTIVITY" in r["text"] else "other"
        for r in records if not r["indexable"])))


def residual_phone(records):
    """Counts only; the values are never printed."""
    from src.extraction import PII
    print("== Residual phone pattern (current src.extraction pattern)")
    hits = collections.Counter()
    for r in records:
        for field in ("text", "tables_markdown"):
            hits[(r["doc_id"], r["page"], field)] += len(PII["phone"].findall(r.get(field) or ""))
    found = {k: v for k, v in hits.items() if v}
    print("matches:", sum(found.values()), "| records:", len({(d, p) for d, p, _ in found}))
    for (doc, page, field), n in sorted(found.items()):
        print(f"  {doc} p{page} {field}: {n}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--part", choices=["a", "b", "all"], default="all")
    args = parser.parse_args()
    OUTPUT, MANIFEST = args.output, args.manifest
    records, manifest = load()
    if args.part in ("a", "all"):
        population(records, manifest)
        raw_hashes(manifest)
        uniqueness(records)
        consistency(records)
        sample(records)
    if args.part in ("b", "all"):
        rule_v1(records, manifest)
        rule_v2(records, manifest)
        coverage(records)
        residual_phone(records)
