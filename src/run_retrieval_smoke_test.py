"""Run the 36 course/skill retrieval comparisons without generating answers."""
from __future__ import annotations

from pathlib import Path
from time import perf_counter

from src.build_indexes import Retriever
from src.common import COURSES, LEVELS, base_parser, evidence_levels, fingerprint, md, read_json, write_json
from src.pipeline_b_indsf_skills import verify_benchmark


def level_status(course: dict, level: str, hits: list[dict]) -> str:
    if not course["level_availability"][level]:
        if course.get("level_status", {}).get(level) == "processing_failed":
            return "INSUFFICIENT_EVIDENCE (Document Processing Failed)"
        return "INSUFFICIENT_EVIDENCE (Folder Empty)"
    status = "CANDIDATES_RETRIEVED" if hits else "NO_RETRIEVABLE_CHUNKS"
    if course.get("level_status", {}).get(level) == "available_with_errors":
        status += " (Partial Document Availability)"
    return status


def hit_description(hits: list[dict]) -> str:
    descriptions = []
    for i, hit in enumerate(hits, 1):
        snippet = md(hit["snippet"]) if hit["snippet"] else "(No native/OCR text)"
        description = f"{i}. {md(hit['doc_id'])}, p{hit['pdf_page_no']}, score={hit['score']:.4f}, " + (
            f"level={hit['evidence_level']}, methods={md(', '.join(hit['extraction_methods_used']))}: {snippet}")
        if hit.get("is_auxiliary_evidence"):
            description += f"<br>Auxiliary CLO evidence; original source level: {hit['source_evidence_level']}"
        if hit.get("visual_diagram_summary"):
            description += "<br>Vision summary (generated, not a quote): " + md(hit["visual_diagram_summary"])
        descriptions.append(description)
    return "<br>".join(descriptions) or "No candidates"


def run(output_dir: Path, *, offline: bool = False) -> list[dict]:
    skills = read_json(output_dir / "industry_skills_benchmark.json")
    verify_benchmark(skills, read_json(output_dir / "indsf_raw_extracted.json"),
                     read_json(output_dir / "indsf_all_extracted_skills.json"))
    retriever = Retriever(output_dir, offline=offline)
    lookup = read_json(output_dir / "verbatim_lookup_store.json")
    failures = [{"course_code": code, "doc_id": doc["doc_id"], "status": doc["status"]}
                for code, course in retriever.catalog["courses"].items() for doc in course["documents"]
                if doc["status"] != "ready"]
    logs, dilution_count = [], 0
    report = ["# Retrieval smoke test", "", f"Index mode: **{retriever.manifest['mode']}**.",
              "Both configurations use exactly the same indexable chunks and embeddings. Routed retrieval "
              "uses per-level BM25 and a 0.15 catalog overlap boost; pooled retrieval has no catalog boost.",
              "Explicit CLO definitions in lecture slides also enter the CLO route when CI/CLO files are available. "
              "Their original source level is retained; the pooled corpus contains each page once.",
              "Routed has up to 3 candidates per level; pooled has 3 overall. Scores are normalized within each "
              "search partition and are not calibrated relevance probabilities.",
              "These are retrieval candidates, not supported-coverage decisions. Without relevance labels, "
              "this report cannot measure retrieval accuracy, precision, recall or F1.", ""]
    if failures:
        report += [f"**Partial input corpus: {len(failures)} documents could not be processed.**", ""]
        report.extend(f"- {md(f['course_code'])} / {md(f['doc_id'])}: {f['status']}" for f in failures)
        report.append("")
    for course_code in COURSES:
        course = retriever.catalog["courses"][course_code]
        for skill in sorted(skills, key=lambda s: s["skill_id"]):
            started = perf_counter()
            query = skill["retrieval_query"]
            pooled = retriever.retrieve(course_code, query)
            routed = {}
            for level in LEVELS.values():
                hits = retriever.retrieve(course_code, query, level) if course["level_availability"][level] else []
                routed[level] = {"status": level_status(course, level, hits), "hits": hits}
            for hit in [*pooled, *(hit for result in routed.values() for hit in result["hits"])]:
                key = f"{course_code}::{hit['doc_id']}::{hit['pdf_page_no']}"
                if key not in lookup or (hit["snippet"] and hit["snippet"] not in lookup[key]) or (
                    not hit["snippet"] and not hit.get("visual_diagram_summary")
                ):
                    raise ValueError(f"Retrieved snippet failed verbatim verification: {key}")
                hit["verbatim_verification"] = "passed" if hit["snippet"] else "no_verbatim_text"
            missing_levels = [level for level in ("CLO", "Assessed") if routed[level]["hits"] and
                              not any(level in evidence_levels(h) for h in pooled)]
            dilution_count += bool(missing_levels)
            log = {"course_code": course_code, "skill_id": skill["skill_id"], "query": query,
                   "routed": routed, "pooled": pooled, "pooled_missing_candidate_levels": missing_levels,
                   "elapsed_ms": round((perf_counter() - started) * 1000, 3)}
            logs.append(log)
            report += [f"## {course_code} / {skill['skill_id']}: {md(skill['skill_name'])}", "",
                       f"Query: {md(query)}", "", "| Level | Proposed routed Top-3 | Pooled baseline Top-3 overall |",
                       "| --- | --- | --- |"]
            for i, (level, result) in enumerate(routed.items()):
                baseline = hit_description(pooled) if i == 0 else "Same overall Top-3 listed in CLO row"
                report.append(f"| {level} | STATUS: {result['status']}<br>{hit_description(result['hits'])} | {baseline} |")
            if missing_levels:
                label = "Potential lecture-slide dilution" if any(h["evidence_level"] == "Taught" for h in pooled) else "Pooled level omission"
                report += ["", "**" + label + ": pooled Top-3 omitted " +
                           ", ".join(missing_levels) + " while routed retrieval returned candidates. "
                           "Manual relevance review is required.**"]
            report += ["", f"Retrieval time: {log['elapsed_ms']:.1f} ms (excludes model loading).", ""]
    report += [f"Completed {len(logs)} course/skill queries; {dilution_count} comparisons have potential level dilution."]
    write_json(output_dir / "retrieval_smoke_test_log.json", {"index_mode": retriever.manifest["mode"],
                    "index_source_fingerprint": retriever.manifest["source_fingerprint"],
                    "benchmark_fingerprint": fingerprint(skills), "input_document_failures": failures, "queries": logs})
    (output_dir / "retrieval_smoke_test_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Completed {len(logs)} retrieval comparisons")
    return logs


def main() -> None:
    parser = base_parser(__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    run(args.output_dir, offline=args.offline)


if __name__ == "__main__":
    main()
