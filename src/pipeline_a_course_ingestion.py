"""Build course catalog, page chunks, safe verbatim lookup and quality report."""
from __future__ import annotations

import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf as fitz

from src.curriculum_scope import explicit_clo_statement, refresh_auxiliary_clo_pages
from src.common import COURSES, LEVELS, base_parser, extraction_options, md, normalize, write_json
from src.extraction import PDFExtractor, extractor_from_args
from src.step0_normalize_formats import normalize_formats

CATALOG_HEADING = re.compile(
    r"\b(?:topic\s+learning\s+outcomes?|course\s+learning\s+outcomes?|learning\s+outcomes?|"
    r"at\s+the\s+end\s+of\s+this[^\n]*|meeting\s+(?:\d+\s+)?overview|course\s+overview|"
    r"outline|agenda|pelajar\s+akan\s+dapat|"
    r"hasil\s+pembelajaran(?:\s+topik|\s+kursus)?)\b|\btopic\s+\d+\s*:", re.I,
)
CATALOG_FOOTER = re.compile(
    r"(?:faculty\s+of(?:\s+artificial\s+intelligence)?|artificial\s+intelligence|"
    r"universiti\s+teknologi\s+malaysia|UTM|\d{1,3})[.,\s]*", re.I,
)


def strip_catalog_footer(text: str) -> str:
    lines = text.splitlines()
    while lines and (not lines[-1].strip() or CATALOG_FOOTER.fullmatch(lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


def skip_reason(text: str, seen_agendas: set[str], has_visual_content: bool = False) -> str | None:
    key = normalize(text).casefold()
    words = re.findall(r"[a-z]+", key)
    if re.fullmatch(r"(?:thank you|thanks|knowledge check|questions|end of (?:topic|lecture))[\W\d]*", key):
        return "divider"
    if len(words) < 4 and not has_visual_content:
        return "low_information"
    if len(words) < 22 and re.match(r"(?:class activity|knowledge check|discussion|thank you)\b", key):
        return "activity_without_explanation"
    if re.search(r"\bagenda\b|meeting overview", key):
        if key in seen_agendas:
            return "duplicate_agenda"
        seen_agendas.add(key)
    return None


def aspect_card(doc_id: str, pages: list[dict]) -> dict:
    first = pages[0] if pages else {}
    title_lines = first.get("native_text", "").splitlines() or first.get("ocr_extracted_text", "").splitlines()
    outcomes, outcome_pages = [], []
    for page in pages[:6]:
        text = "\n".join(strip_catalog_footer(page[field]) for field in ("native_text", "ocr_extracted_text"))
        match = CATALOG_HEADING.search(text)
        if match:
            outcome_pages.append(page["pdf_page_no"])
            outcomes.extend(line.strip(" -\u2022\t") for line in text[match.end():].splitlines()
                            if len(line.strip()) > 3)
    return {
        "doc_id": doc_id, "deck_title": first.get("slide_or_section_title") or " ".join(title_lines[:2]),
        "declared_learning_outcomes_or_agenda": list(dict.fromkeys(outcomes)),
        "aspect_scan_pdf_pages": [p["pdf_page_no"] for p in pages[:6]],
        "outcome_source_pages": outcome_pages,
        "embedded_clo_pages": [p["pdf_page_no"] for p in pages
                               if explicit_clo_statement(p["verbatim_text_span"])],
        "embedded_assessment_pages": [p["pdf_page_no"] for p in pages
                                      if re.search(r"(?:assignment|assessment|rubric|project brief)\b.{0,100}"
                                                   r"(?:\d+\s*%|submit|deadline|task|criteria|marks)",
                                                   p["verbatim_text_span"], re.I)],
    }


_worker_extractor = None


def initialize_worker(config, cache_dir):
    global _worker_extractor
    _worker_extractor = PDFExtractor(config, cache_dir)


def extract_in_worker(path: str, force_ocr: bool = False) -> list[dict]:
    return list(_worker_extractor.extract(Path(path), force_ocr=force_ocr))


def ingest(data_dir: Path, output_dir: Path, extractor, workers: int = 1) -> dict:
    if workers < 1:
        raise ValueError("workers must be positive")
    records = normalize_formats(data_dir, output_dir)
    extracted, extraction_errors = {}, {}
    if workers > 1:
        ready = {r["pdf_path"]: Path(r["source_relative_path"]).parts[1] == "01_CI_CLO"
                 for r in records if r["status"] == "ready" and
                 any(Path(r["source_relative_path"]).parts[0].startswith(code) for code in COURSES) and
                 len(Path(r["source_relative_path"]).parts) >= 3 and
                 Path(r["source_relative_path"]).parts[1] in LEVELS}
        with ProcessPoolExecutor(max_workers=workers, initializer=initialize_worker,
                                 initargs=(extractor.config, extractor.cache_dir)) as pool:
            futures = {pool.submit(extract_in_worker, path, ready[path]): path for path in sorted(ready)}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    extracted[path] = future.result()
                    print(f"Parsed {Path(path).name}: {len(extracted[path])} pages", flush=True)
                except (fitz.FileDataError, RuntimeError, ValueError, OSError) as error:
                    extraction_errors[path] = f"{type(error).__name__}: {error}"
    catalog = {"schema_version": 1, "courses": {}, "normalization_manifest": "normalization_manifest.json"}
    chunks, lookup, quality = [], {}, []
    for code, title in COURSES.items():
        folders = sorted(p for p in (data_dir / "courses").glob(code + "*") if p.is_dir())
        course = {"course_code": code, "course_title": title,
                  "course_folders": [p.name for p in folders],
                  "level_availability": {level: False for level in LEVELS.values()},
                  "level_status": {}, "documents": [], "deck_aspect_cards": []}
        catalog["courses"][code] = course
        used_ids = set()
        for record in records:
            relative = Path(record["source_relative_path"])
            if len(relative.parts) < 3 or relative.parts[0] not in {p.name for p in folders}:
                continue
            level = LEVELS.get(relative.parts[1])
            if level is None:
                continue
            doc_id = relative.with_suffix(".pdf").name
            if doc_id in used_ids:
                doc_id = relative.as_posix() + ".pdf"
            used_ids.add(doc_id)
            metadata = {**record, "doc_id": doc_id, "evidence_level": level}
            course["documents"].append(metadata)
            if record["status"] != "ready":
                quality.append({"course_code": code, "doc_id": doc_id, "error": record["error"], "status": record["status"]})
                continue
            print(f"Extracting {code}/{level}/{doc_id}", flush=True)
            try:
                if record["pdf_path"] in extraction_errors:
                    raise RuntimeError(extraction_errors[record["pdf_path"]])
                pages = extracted[record["pdf_path"]] if workers > 1 else list(extractor.extract(
                    Path(record["pdf_path"]), force_ocr=level == "CLO"))
            except (fitz.FileDataError, RuntimeError, ValueError, OSError) as error:
                metadata.update(status="extraction_failed", error=f"{type(error).__name__}: {error}")
                quality.append({"course_code": code, "doc_id": doc_id, "error": metadata["error"], "status": metadata["status"]})
                continue
            course["level_availability"][level] = bool(pages) or course["level_availability"][level]
            metadata["page_count"] = len(pages)
            if level == "Taught":
                course["deck_aspect_cards"].append(aspect_card(doc_id, pages))
            seen_agendas = set()
            for page in pages:
                number = page["pdf_page_no"]
                visual = bool(page["visual_diagram_summary"]) or (page["image_area_fraction"] > .25 and
                                                                                bool(page["verbatim_text_span"]))
                reason = skip_reason(page["verbatim_text_span"], seen_agendas, visual) if level == "Taught" else (
                    "empty_page" if not page["verbatim_text_span"] else None)
                chunk = {
                    "chunk_id": f"{code}__{doc_id}__p{number:02d}", "course_code": code,
                    "evidence_level": level, "doc_id": doc_id, "original_format": record["original_format"],
                    "slide_or_section_title": next(iter(page["native_text"].splitlines()), ""),
                    **page, "indexable": reason is None, "skip_reason": reason,
                    "auxiliary_evidence_levels": [],
                }
                chunks.append(chunk)
                lookup[f"{code}::{doc_id}::{number}"] = page["verbatim_text_span"]
                quality.append({"course_code": code, "doc_id": doc_id, **page, "skip_reason": reason})
        for level in LEVELS.values():
            docs = [d for d in course["documents"] if d["evidence_level"] == level]
            course["level_status"][level] = (
                "available_with_errors" if course["level_availability"][level] and any(d["status"] != "ready" for d in docs)
                else "available" if course["level_availability"][level]
                else "processing_failed" if docs else "folder_empty_or_missing"
            )
    refresh_auxiliary_clo_pages(chunks, catalog)
    if len(lookup) != len(chunks) or len({c["chunk_id"] for c in chunks}) != len(chunks):
        raise ValueError("Document IDs collided; refusing to overwrite provenance")
    write_json(output_dir / "course_catalog_manifest.json", catalog)
    write_json(output_dir / "parsed_course_chunks.json", chunks)
    write_json(output_dir / "verbatim_lookup_store.json", lookup)
    # Page-level text already lives in chunks; quality telemetry stores only event metadata.
    chunk_events = {(c["course_code"], c["doc_id"], c["pdf_page_no"]): c for c in chunks}
    for row in quality:
        if "pdf_page_no" in row:
            chunk = chunk_events[(row["course_code"], row["doc_id"], row["pdf_page_no"])]
            row.update(skip_reason=chunk["skip_reason"], auxiliary_evidence_levels=chunk["auxiliary_evidence_levels"])
    telemetry = [{k: v for k, v in row.items() if k not in {
        "native_text", "ocr_extracted_text", "verbatim_text_span", "tables_markdown", "visual_diagram_summary"
    }} for row in quality]
    write_json(output_dir / "course_ingestion_events.json", telemetry)
    report = ["# Ingestion quality report", "", f"Documents: {len(records)}; pages: {len(chunks)}; "
              f"indexable: {sum(c['indexable'] for c in chunks)}.",
              f"OCR enabled: {extractor.config.enable_ocr}; vision enabled: {extractor.config.enable_vision_llm}.", "",
              "Redaction counts record extraction events (native, OCR, tables, vision), not unique people.", "",
              "## Folder availability", "", "| Course | CLO | Taught | Assessed |", "| --- | --- | --- | --- |"]
    for code, course in catalog["courses"].items():
        report.append("| " + " | ".join([code, *course["level_status"].values()]) + " |")
    report += ["", "## Auxiliary CLO memberships", "",
               "Explicit CLO pages from lecture slides retain their source level and verbatim lookup key. They also enter the CLO route "
               "only when a usable CI/CLO document exists; the pooled corpus keeps each page once.", "",
               "| Course | Document | PDF page | Source level |", "| --- | --- | --- | --- |"]
    for code, course in catalog["courses"].items():
        report.extend(f"| {code} | {md(p['doc_id'])} | {p['pdf_page_no']} | {p['source_evidence_level']} |"
                      for p in course["auxiliary_clo_pages"])
    report += ["", "## Page events", "", "| Course / document | PDF page | Event |", "| --- | --- | --- |"]
    for row in telemetry:
        events = []
        if row.get("error"):
            events.append(row["status"] + ": " + row["error"])
        if row.get("ocr_triggered"):
            events.append("OCR " + row["ocr_status"] + (" (forced full page for CI/CLO)" if row.get("ocr_forced") else ""))
        if row.get("vision_triggered"):
            events.append(row.get("vision_error") or ("vision summary extracted" if
                          "ollama_vision" in row.get("extraction_methods_used", []) else "vision returned no summary"))
        if row.get("skip_reason"):
            events.append("dropped from indexes: " + row["skip_reason"])
        events.extend(f"PII redacted: {e['kind']} at offset {e['offset']}" for e in row.get("redaction_events", []))
        if events:
            report.append(f"| {md(row['course_code'] + '/' + row['doc_id'])} | {row.get('pdf_page_no', '-')} | {md('; '.join(events))} |")
    report += ["", "Verbatim lookup contains the normalized, PII-redacted native + OCR union for every parsed page, "
               "including dropped pages. Vision summaries and Markdown table formatting are separate fields.",
               "", "IndSF extraction telemetry is recorded separately in [indsf_quality_report.md](indsf_quality_report.md)."]
    if (output_dir / "vision_smoke_test_sample.json").is_file():
        report += ["", "A separate live vision API sample is available in [vision_smoke_test_sample.json](vision_smoke_test_sample.json). "
                   "Its generated description is separate from this run's native/OCR corpus."]
    (output_dir / "ingestion_quality_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return catalog


def main() -> None:
    parser = base_parser(__doc__)
    extraction_options(parser)
    parser.add_argument("--allow-partial", action="store_true", help="Exit successfully with recorded document failures")
    parser.add_argument("--workers", type=int, default=1, help="Separate extraction processes; 2 is useful on multicore CPUs")
    args = parser.parse_args()
    catalog = ingest(args.data_dir, args.output_dir, extractor_from_args(args), args.workers)
    failures = [d for c in catalog["courses"].values() for d in c["documents"] if d["status"] != "ready"]
    print(f"Course ingestion complete; {len(failures)} document failures")
    if failures and not args.allow_partial:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
