"""Audit generated provenance, privacy, corpus parity and all 36 retrieval logs."""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from src.common import COURSES, LEVELS, base_parser, evidence_levels, fingerprint, normalize, read_json, write_json
from src.extraction import clean
from src.pipeline_b_indsf_skills import verify_benchmark
from src.pipeline_a_course_ingestion import explicit_clo_statement


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(output_dir: Path) -> dict:
    chunks = read_json(output_dir / "parsed_course_chunks.json")
    catalog = read_json(output_dir / "course_catalog_manifest.json")
    lookup = read_json(output_dir / "verbatim_lookup_store.json")
    raw = read_json(output_dir / "indsf_raw_extracted.json")
    skills = read_json(output_dir / "industry_skills_benchmark.json")
    index = read_json(output_dir / "indexes/manifest.json")
    indexed_chunks = read_json(output_dir / "indexes/chunks.json")
    indexed_catalog = read_json(output_dir / "indexes/catalog.json")
    log = read_json(output_dir / "retrieval_smoke_test_log.json")
    require(set(catalog["courses"]) == set(COURSES), "Catalog must contain all three courses")
    require(len({c["chunk_id"] for c in chunks}) == len(chunks), "Duplicate chunk IDs")
    expected_lookup, document_pages = {}, defaultdict(set)
    chunk_by_id = {c["chunk_id"]: c for c in indexed_chunks}
    for chunk in chunks:
        key = f"{chunk['course_code']}::{chunk['doc_id']}::{chunk['pdf_page_no']}"
        require(chunk["course_code"] in COURSES and chunk["evidence_level"] in LEVELS.values(), f"Invalid routing: {key}")
        require(isinstance(chunk["pdf_page_no"], int) and chunk["pdf_page_no"] >= 1, f"Invalid page number: {key}")
        require(chunk["original_format"] in {"pdf", "pptx", "docx"}, f"Invalid original format: {key}")
        union = normalize("\n".join(filter(None, [chunk["native_text"], chunk["ocr_extracted_text"]])))
        require(chunk["verbatim_text_span"] == union, f"Verbatim provenance mismatch: {key}")
        require(key not in expected_lookup, f"Duplicate provenance key: {key}")
        expected_lookup[key] = union
        document_pages[(chunk["course_code"], chunk["doc_id"])].add(chunk["pdf_page_no"])
        if chunk.get("auxiliary_evidence_levels"):
            require(chunk["auxiliary_evidence_levels"] == ["CLO"] and chunk["evidence_level"] == "Taught" and
                    catalog["courses"][chunk["course_code"]]["level_availability"]["CLO"] and
                    explicit_clo_statement(chunk["verbatim_text_span"]), f"Invalid auxiliary CLO membership: {key}")
        if chunk["evidence_level"] == "CLO":
            require(chunk["ocr_forced"] and chunk["table_extraction_status"] == "completed", f"CI extraction not forced: {key}")
            if chunk["ocr_status"] != "disabled":
                require(chunk["ocr_status"] == "completed" and not chunk["ocr_native_word_masking"], f"Incomplete full-page CI OCR: {key}")
    require(lookup == expected_lookup, "Lookup does not match all parsed pages")
    for page in [*chunks, *raw]:
        for field in ("native_text", "ocr_extracted_text", "visual_diagram_summary", "tables_markdown"):
            _, events = clean(page.get(field, ""), boilerplate=False)
            require(not events, f"Residual regex-detectable PII: {page['doc_id']} p{page['pdf_page_no']} field {field}")
    for code, course in catalog["courses"].items():
        for document in course["documents"]:
            if document["status"] == "ready":
                require(document_pages[(code, document["doc_id"])] == set(range(1, document["page_count"] + 1)),
                        f"Missing parsed pages in {code}/{document['doc_id']}")
        for level in LEVELS.values():
            valid = any(d["evidence_level"] == level and d["status"] == "ready" and d["page_count"] > 0
                        for d in course["documents"])
            require(course["level_availability"][level] == valid, f"Incorrect availability: {code}/{level}")
    b1_path = output_dir / "indsf_all_extracted_skills.json"
    verify_benchmark(skills, raw, read_json(b1_path))
    require(index["source_fingerprint"] == fingerprint({"chunks": chunks, "catalog": catalog}), "Stale source index")
    require(index["index_fingerprint"] == fingerprint({"chunks": indexed_chunks, "catalog": indexed_catalog}), "Stale index snapshot")
    require([c for c in chunks if c["indexable"] and (c["verbatim_text_span"] or c["visual_diagram_summary"])] == indexed_chunks,
            "Indexed corpus differs from eligible chunks")
    embedding_file = output_dir / "indexes/embeddings.npy"
    require(hashlib.sha256(embedding_file.read_bytes()).hexdigest() == index["embedding_sha256"], "Embedding checksum mismatch")
    embeddings = np.load(embedding_file, allow_pickle=False)
    require(list(embeddings.shape) == index["embedding_shape"] and np.isfinite(embeddings).all(), "Invalid embedding matrix")
    for code in COURSES:
        pooled = index["partitions"]["pooled"][code]
        routed = [i for level in LEVELS.values() for i in index["partitions"]["routed"][f"{code}::{level}"]]
        require(set(pooled) == set(routed) and len(pooled) == len(set(pooled)), f"Corpus parity failed: {code}")
        for level in LEVELS.values():
            rows = index["partitions"]["routed"][f"{code}::{level}"]
            expected = [i for i in pooled if level in evidence_levels(indexed_chunks[i]) and catalog["courses"][code]["level_availability"][level]]
            require(rows == expected, f"Incorrect routed membership: {code}/{level}")
    queries = log["queries"]
    require(log["index_source_fingerprint"] == index["source_fingerprint"], "Retrieval log refers to a different source corpus")
    require(log["benchmark_fingerprint"] == fingerprint(skills), "Retrieval log refers to a different skill benchmark")
    expected_pairs = {(code, s["skill_id"]) for code in COURSES for s in skills}
    skill_queries = {s["skill_id"]: s["retrieval_query"] for s in skills}
    require(len(queries) == 36 and {(q["course_code"], q["skill_id"]) for q in queries} == expected_pairs,
            "Smoke test must contain exactly all 36 course/skill pairs")
    for query in queries:
        require(query["query"] == skill_queries[query["skill_id"]], "Retrieval query differs from the locked benchmark")
        course = catalog["courses"][query["course_code"]]
        require(set(query["routed"]) == set(LEVELS.values()), "Missing routed levels")
        require(len(query["pooled"]) <= 3, "Too many pooled hits")
        for level, result in query["routed"].items():
            require(len(result["hits"]) <= 3, "Too many routed hits")
            require(all(h["evidence_level"] == level for h in result["hits"]), "Cross-level routing leak")
            if not course["level_availability"][level]:
                require(not result["hits"] and result["status"].startswith("INSUFFICIENT_EVIDENCE"), "Missing-level abstention failed")
        for hit in [*query["pooled"], *(h for r in query["routed"].values() for h in r["hits"])]:
            key = f"{query['course_code']}::{hit['doc_id']}::{hit['pdf_page_no']}"
            require(hit["chunk_id"] in chunk_by_id, "Hit outside indexed corpus")
            require(key in lookup, "Hit has no source-page lookup key")
            if hit["snippet"]:
                require(hit["snippet"] in lookup[key], "Hit snippet is not verbatim")
            else:
                require(bool(hit.get("visual_diagram_summary")) and hit["verbatim_verification"] == "no_verbatim_text",
                        "An empty quote must be explicitly labeled as a visual-only candidate")
            require(hit["course_code"] == query["course_code"], "Cross-course routing leak")
            require(hit["source_evidence_level"] == chunk_by_id[hit["chunk_id"]]["evidence_level"], "Source level was overwritten")
    summary = {
        "status": "passed", "course_pages": len(chunks), "indexable_chunks": len(indexed_chunks),
        "indsf_pages": len(raw), "skills": len(skills), "queries": len(queries),
        "index_mode": index["mode"], "document_failures": log["input_document_failures"],
        "source_fingerprint": index["source_fingerprint"], "benchmark_fingerprint": fingerprint(skills),
        "course_ocr_pages": sum(c["ocr_status"] == "completed" for c in chunks),
        "redaction_events": sum(len(c["redaction_events"]) for c in chunks),
        "dropped_page_reasons": dict(Counter(c["skip_reason"] for c in chunks if c["skip_reason"])),
        "potential_dilution_queries": sum(bool(q["pooled_missing_candidate_levels"]) for q in queries),
        "auxiliary_clo_pages": sum("CLO" in c.get("auxiliary_evidence_levels", []) for c in chunks),
    }
    write_json(output_dir / "artifact_validation_report.json", summary)
    print(f"Artifact validation passed: {len(chunks)} course pages, {len(skills)} skills, {len(queries)} queries")
    return summary


def main() -> None:
    args = base_parser(__doc__).parse_args()
    validate(args.output_dir)


if __name__ == "__main__":
    main()
