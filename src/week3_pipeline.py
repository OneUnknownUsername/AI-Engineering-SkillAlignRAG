"""Week 3 V1 data pipeline: stage contracts and lineage around the existing extractors.

SOURCE -> INGEST -> INSPECT -> PREPARE -> VALIDATE -> RECORD LINEAGE, stopping at
prepared page records. Embeddings, indexes and model judgement are later stages.
Extraction always runs without the document cache, so a rerun re-extracts every page
and the repeatability check compares real work rather than two cache reads.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import hashlib
import io
import json
import multiprocessing
import os
import platform
import re
import shutil
import statistics
import subprocess
import tempfile
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from src.common import ROOT, read_json, write_json
from src.extraction import PII, ExtractionConfig, PDFExtractor
from src.indsf_extraction import extract_all_skills
from src.pipeline_a_course_ingestion import ingest
from src.pipeline_b_indsf_skills import extract_indsf

PIPELINE_VERSION = "week3-v1"
COURSE_KIND = "course_documents"
INDSF_KIND = "indsf_documents"
KINDS = (COURSE_KIND, INDSF_KIND)
COURSE_METHOD = "page-level records; native text + RapidOCR union; PII regex redaction; vision disabled"
INDSF_METHOD = COURSE_METHOD + "; structured B1 item extraction (no embeddings)"
ACCESS_RIGHTS = {
    COURSE_KIND: "Internal UTM course material; redistribution permission not verified; do not publish",
    INDSF_KIND: "HRD Corp publication; licence terms not verified",
}
OWNERS = {COURSE_KIND: "UTM Faculty of Artificial Intelligence (course teaching team)", INDSF_KIND: "HRD Corp"}


class PipelineStageError(RuntimeError):
    """A stage contract failed; the run stops instead of producing partial evidence."""

    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


@dataclass
class Extraction:
    kind: str
    sources: list[dict]
    outputs: dict[str, list[dict]]
    inspection: dict
    method: str
    known_gaps: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    comparison_pages: list[dict] = field(default_factory=list, repr=False)  # Not written to disk.


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


@contextlib.contextmanager
def _quiet():
    """Keep per-document progress and ONNX thread warnings out of notebook evidence."""
    saved = os.dup(1), os.dup(2)
    sink = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(sink, 1)
        os.dup2(sink, 2)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for descriptor in (*saved, sink):
            os.close(descriptor)


def _extractor(enable_ocr: bool, ocr_threads: int) -> PDFExtractor:
    return PDFExtractor(ExtractionConfig(enable_ocr, False, "qwen2.5vl:3b", "http://localhost:11434/api/generate",
                                         ocr_threads=ocr_threads), None)


def _redaction_counts(pages: list[dict]) -> dict:
    return dict(sorted(Counter(event["kind"] for page in pages for event in page.get("redaction_events", [])).items()))


def check_source_integrity(directory: Path) -> None:
    """Stop on truncated files: PDF repair can open them with silently blank pages."""
    damaged = []
    for path in sorted(Path(directory).rglob("*")):
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            with path.open("rb") as handle:
                handle.seek(max(path.stat().st_size - 2048, 0))
                if b"%%EOF" not in handle.read():
                    damaged.append(f"{path.name}: no PDF end marker")
        elif suffix in {".pptx", ".docx"}:
            try:
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None:
                        damaged.append(f"{path.name}: corrupt archive member")
            except zipfile.BadZipFile:
                damaged.append(f"{path.name}: not a complete Office archive")
    if damaged:
        raise PipelineStageError("ingest", "Damaged source files: " + "; ".join(damaged))


def extract_courses(root: Path = ROOT, *, enable_ocr: bool = True, workers: int = 6, ocr_threads: int = 2) -> Extraction:
    """INGEST and INSPECT course files by calling Pipeline A unchanged."""
    started = time.perf_counter()
    root = Path(root)
    check_source_integrity(root / "data/courses")
    if workers > 1:
        # Forking a live notebook kernel can deadlock; spawned workers start clean.
        multiprocessing.set_start_method("spawn", force=True)
    with tempfile.TemporaryDirectory() as workspace:
        workspace = Path(workspace)
        converted = root / "outputs/normalized_pdf"
        if converted.is_dir():
            # Valid conversions are reused so the run does not require LibreOffice on this machine.
            shutil.copytree(converted, workspace / "normalized_pdf")
        with _quiet():
            catalog = ingest(root / "data", workspace, _extractor(enable_ocr, ocr_threads), workers)
        chunks = read_json(workspace / "parsed_course_chunks.json")
        documents = [dict(document, course_code=code) for code, course in catalog["courses"].items()
                     for document in course["documents"]]
        failures = [f"{d['source_relative_path']}: {d['status']} ({d['error']})" for d in documents if d["status"] != "ready"]
        if failures:
            raise PipelineStageError("ingest", "; ".join(failures))
        if not documents:
            raise PipelineStageError("ingest", "No course documents found under data/courses")
        for document in documents:
            source = root / "data/courses" / document["source_relative_path"]
            document["source"] = relative(source, root)
            document["source_sha256"] = sha256_file(source)
            document["normalized_pdf_sha256"] = (sha256_file(Path(document["pdf_path"]))
                                                 if document["original_format"] != "pdf" else None)
    by_document = {(d["course_code"], d["doc_id"]): d for d in documents}
    records = []
    for chunk in chunks:
        document = by_document[(chunk["course_code"], chunk["doc_id"])]
        records.append({
            "record_id": chunk["chunk_id"], "text": chunk["verbatim_text_span"], "source": document["source"],
            "source_sha256": document["source_sha256"], "processing": COURSE_METHOD, "page": chunk["pdf_page_no"],
            "printed_slide_no": chunk["printed_slide_no"], "course_code": chunk["course_code"],
            "evidence_level": chunk["evidence_level"], "doc_id": chunk["doc_id"],
            "original_format": chunk["original_format"], "tables_markdown": chunk["tables_markdown"],
            "indexable": chunk["indexable"], "skip_reason": chunk["skip_reason"],
            "auxiliary_evidence_levels": chunk["auxiliary_evidence_levels"],
            "extraction_methods_used": chunk["extraction_methods_used"],
            "redaction_count": len(chunk["redaction_events"]),
        })
    counts = Counter(record["source"] for record in records)
    sources = [{
        "path": d["source"], "sha256": d["source_sha256"], "format": d["original_format"],
        "normalized_pdf_sha256": d["normalized_pdf_sha256"], "course_code": d["course_code"],
        "evidence_level": d["evidence_level"], "pages": d["page_count"], "records": counts[d["source"]],
    } for d in sorted(documents, key=lambda item: item["source"])]
    gaps = [{"course_code": code, "evidence_level": level, "status": status}
            for code, course in catalog["courses"].items()
            for level, status in course["level_status"].items() if status != "available"]
    inspection = {
        "documents": len(documents), "pages": len(chunks),
        "documents_by_format": dict(sorted(Counter(d["original_format"] for d in documents).items())),
        "pages_by_level": dict(sorted(Counter(c["evidence_level"] for c in chunks).items())),
        "level_status": {code: course["level_status"] for code, course in catalog["courses"].items()},
        "ocr_pages": sum(c["ocr_triggered"] for c in chunks),
        "empty_text_pages": sum(not c["verbatim_text_span"] for c in chunks),
        "indexable_pages": sum(c["indexable"] for c in chunks),
        "skip_reasons": dict(sorted(Counter(c["skip_reason"] for c in chunks if c["skip_reason"]).items())),
        "redaction_events": _redaction_counts(chunks),
    }
    extraction = Extraction(COURSE_KIND, sources, {"prepared_text.jsonl": records}, inspection, COURSE_METHOD, gaps,
                            comparison_pages=chunks)
    extraction.seconds = round(time.perf_counter() - started, 1)
    return extraction


def extract_benchmark(root: Path = ROOT, *, enable_ocr: bool = True, ocr_threads: int = 8) -> Extraction:
    """INGEST and INSPECT the IndSF PDFs through Pipeline B stage B1 (no embedding model)."""
    started = time.perf_counter()
    root = Path(root)
    check_source_integrity(root / "data/industry_benchmark")
    with tempfile.TemporaryDirectory() as workspace:
        try:
            with _quiet():
                pages = extract_indsf(root / "data", Path(workspace), _extractor(enable_ocr, ocr_threads))
        except ValueError as error:
            raise PipelineStageError("ingest", str(error)) from error
    if not pages:
        raise PipelineStageError("ingest", "No IndSF pages were extracted")
    hashes = {doc_id: sha256_file(root / "data/industry_benchmark" / doc_id) for doc_id in {p["doc_id"] for p in pages}}
    records = [{
        "record_id": f"{page['doc_id']}__p{page['pdf_page_no']:02d}", "text": page["verbatim_text_span"],
        "source": f"data/industry_benchmark/{page['doc_id']}", "source_sha256": hashes[page["doc_id"]],
        "processing": INDSF_METHOD, "page": page["pdf_page_no"], "framework": page["framework"],
        "doc_id": page["doc_id"], "tables_markdown": page["tables_markdown"],
        "extraction_methods_used": page["extraction_methods_used"], "redaction_count": len(page["redaction_events"]),
    } for page in pages]
    items = extract_all_skills(pages)
    counts = Counter(record["source"] for record in records)
    sources = [{"path": f"data/industry_benchmark/{doc_id}", "sha256": digest, "format": "pdf", "normalized_pdf_sha256": None,
                "course_code": None, "evidence_level": "Industry benchmark",
                "pages": counts[f"data/industry_benchmark/{doc_id}"], "records": counts[f"data/industry_benchmark/{doc_id}"]}
               for doc_id, digest in sorted(hashes.items())]
    inspection = {
        "documents": len(hashes), "pages": len(pages), "structured_items": len(items),
        "items_by_section": dict(sorted(Counter(item["section_type"] for item in items).items())),
        "ocr_pages": sum(p["ocr_triggered"] for p in pages),
        "empty_text_pages": sum(not p["verbatim_text_span"] for p in pages),
        "redaction_events": _redaction_counts(pages),
    }
    extraction = Extraction(INDSF_KIND, sources, {"prepared_indsf_text.jsonl": records, "prepared_indsf_items.jsonl": items},
                            inspection, INDSF_METHOD)
    extraction.seconds = round(time.perf_counter() - started, 1)
    return extraction


def extract(kind: str, root: Path = ROOT, **options) -> Extraction:
    if kind == COURSE_KIND:
        return extract_courses(root, **options)
    if kind == INDSF_KIND:
        options.pop("workers", None)
        return extract_benchmark(root, **options)
    raise ValueError(f"Unknown pipeline kind: {kind}")


def _residual_pii(rows: list[dict]) -> dict:
    found = Counter()
    for row in rows:
        text = " ".join(str(row.get(name, "")) for name in ("text", "tables_markdown", "verbatim_text"))
        for kind, pattern in PII.items():
            found[kind] += len(pattern.findall(text))
    return {kind: found[kind] for kind in PII}


def store_and_validate(extraction: Extraction, directory: Path, root: Path = ROOT) -> dict:
    """PREPARE/STORE then VALIDATE: a non-empty file alone is not accepted as correct output."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written, pii = [], Counter()
    for name, rows in extraction.outputs.items():
        target = directory / name
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if not rows or target.stat().st_size == 0:
            raise PipelineStageError("validate", f"Prepared output is empty: {name}")
        with target.open(encoding="utf-8") as handle:
            if [json.loads(line) for line in handle] != rows:
                raise PipelineStageError("validate", f"Read-back differs from prepared rows: {name}")
        pii.update(_residual_pii(rows))
        written.append(target)
    pages = next(rows for name, rows in extraction.outputs.items() if name.endswith("_text.jsonl"))
    if len({row["record_id"] for row in pages}) != len(pages):
        raise PipelineStageError("validate", "Duplicate record IDs")
    if any(not isinstance(row["page"], int) or row["page"] < 1 for row in pages):
        raise PipelineStageError("validate", "A record has no valid page reference")
    known = {source["path"]: source for source in extraction.sources}
    for row in pages:
        if known.get(row["source"], {}).get("sha256") != row["source_sha256"]:
            raise PipelineStageError("validate", f"Record does not match a registered source: {row['record_id']}")
    mismatched = [s["path"] for s in extraction.sources if s["pages"] != s["records"]]
    if mismatched:
        raise PipelineStageError("validate", f"Page count differs from record count: {mismatched}")
    if sum(pii.values()):
        raise PipelineStageError("validate", f"PII patterns remain after redaction: {dict(pii)}")
    return {
        "output_count": len(written), "outputs": [relative(path, root) for path in written],
        "output_sha256": [sha256_file(path) for path in written],
        "output_bytes": [path.stat().st_size for path in written],
        "output_records": [len(rows) for rows in extraction.outputs.values()],
        "residual_pii_pattern_matches": {kind: pii[kind] for kind in PII},
    }


def _git_commit(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "unknown"


def _environment() -> dict:
    packages = ("PyMuPDF", "pdfplumber", "rapidocr-onnxruntime", "onnxruntime", "Pillow")
    versions = {}
    for package in packages:
        with contextlib.suppress(metadata.PackageNotFoundError):
            versions[package] = metadata.version(package)
    return {"python": platform.python_version(), "platform": platform.system(), "packages": versions}


def execute_pipeline(kind: str, root: Path = ROOT, pipeline_dir: Path | None = None, **options) -> dict:
    """Run every stage for one data branch and write its pipeline_manifest.json."""
    root = Path(root)
    directory = (Path(pipeline_dir) if pipeline_dir else root / "data/pipeline_v1") / kind
    extraction = extract(kind, root, **options)
    validation = store_and_validate(extraction, directory, root)
    text_output = next(path for path in validation["outputs"] if path.endswith("_text.jsonl"))
    record = {
        "pipeline_version": PIPELINE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(root),
        "data_type": kind,
        "stages": ["source", "ingest", "inspect", "prepare", "validate", "record_lineage"],
        "configuration": {"extraction_cache": "disabled", "ocr": options.get("enable_ocr", True), "vision_llm": False},
        "processing_method": extraction.method,
        "sources": [{"path": s["path"], "sha256": s["sha256"], "normalized_pdf_sha256": s["normalized_pdf_sha256"]}
                    for s in extraction.sources],
        "outputs": validation["outputs"],
        "source_output_mapping": [{"source": s["path"], "output": text_output, "records": s["records"]}
                                  for s in extraction.sources],
        "inspection": extraction.inspection,
        "validation": validation,
        "known_gaps": extraction.known_gaps,
        "source_version": "Not verified",
        "access_rights": ACCESS_RIGHTS[kind],
        "runtime": {"seconds": extraction.seconds, **_environment()},
    }
    write_json(directory / "pipeline_manifest.json", record)
    return record


def compare_runs(first: dict, second: dict) -> dict:
    """Timestamps and runtime may differ; sources, outputs and mappings may not."""
    checks = {name: first[name] == second[name] for name in ("sources", "validation", "source_output_mapping")}
    checks["passed"] = all(checks.values())
    return checks


def build_lineage_manifest(extractions: list[Extraction], processed_dir: Path, manifest_path: Path,
                           root: Path = ROOT) -> dict:
    """Write the common Part B source-to-output manifest with relative paths only."""
    root = Path(root)
    lineage = []
    for extraction in extractions:
        validation = store_and_validate(extraction, processed_dir, root)
        text_name = next(name for name in extraction.outputs if name.endswith("_text.jsonl"))
        output = next(path for path in validation["outputs"] if path.endswith(text_name))
        output_sha = validation["output_sha256"][validation["outputs"].index(output)]
        for source in extraction.sources:
            lineage.append({
                "source_id": f"SRC{len(lineage) + 1:02d}", "source_filename": source["path"],
                "source_sha256": source["sha256"], "normalized_pdf_sha256": source["normalized_pdf_sha256"],
                "original_format": source["format"], "course_code": source["course_code"],
                "evidence_level": source["evidence_level"], "pages": source["pages"], "records": source["records"],
                "prepared_output": output, "prepared_sha256": output_sha, "processing_note": extraction.method,
                "source_version": "Not verified", "owner": OWNERS[extraction.kind],
                "access_rights": ACCESS_RIGHTS[extraction.kind], "status": "Prepared; quality review pending",
            })
    manifest = {
        "pipeline_version": PIPELINE_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(root), "records": lineage,
        "known_gaps": [gap for extraction in extractions for gap in extraction.known_gaps],
    }
    write_json(manifest_path, manifest)
    return manifest


def verify_manifest(manifest_path: Path, root: Path = ROOT) -> int:
    """Recompute every recorded hash. This proves integrity, not data quality or permission to share."""
    root = Path(root)
    records = read_json(manifest_path).get("records", [])
    if not records:
        raise PipelineStageError("record_lineage", "Manifest has no lineage records")
    for record in records:
        for path_field, hash_field in (("source_filename", "source_sha256"), ("prepared_output", "prepared_sha256")):
            target = root / record[path_field]
            if not target.is_file():
                raise PipelineStageError("record_lineage", f"Missing file: {record[path_field]}")
            if sha256_file(target) != record[hash_field]:
                raise PipelineStageError("record_lineage", f"Checksum mismatch: {record[path_field]}")
    return len(records)


def _fixed_spans(text: str, size: int) -> list[tuple[int, int]]:
    return [(start, min(start + size, len(text))) for start in range(0, len(text), size)]


def _paragraph_spans(text: str, size: int) -> list[tuple[int, int]]:
    """The lab's paragraph-aware splitter (Cell 5A1), tracking offsets as well as lengths."""
    spans, start_offset, end_offset, length = [], None, None, 0
    boundaries = [(match.start(), match.end()) for match in re.finditer(r"\n\s*\n", text)] + [(len(text), len(text))]
    cursor = 0
    for stop, following in boundaries:
        raw = text[cursor:stop]
        begin = cursor + len(raw) - len(raw.lstrip())
        segment = raw.strip()
        cursor = following
        if not segment:
            continue
        finish = begin + len(segment)
        if len(segment) > size:
            if start_offset is not None:
                spans.append((start_offset, end_offset))
                start_offset, length = None, 0
            spans.extend((begin + a, begin + b) for a, b in _fixed_spans(segment, size))
        elif length + len(segment) + (2 if length else 0) <= size:
            start_offset = begin if start_offset is None else start_offset
            end_offset = finish
            length += len(segment) + (2 if length else 0)
        else:
            if start_offset is not None:
                spans.append((start_offset, end_offset))
            start_offset, end_offset, length = begin, finish, len(segment)
    if start_offset is not None:
        spans.append((start_offset, end_offset))
    return spans


def compare_chunking(pages: list[dict], size: int = 500) -> list[dict]:
    """Compare page-level records with the lab's two 500-character whole-document splitters."""
    documents: dict[tuple, list[dict]] = {}
    for page in pages:
        documents.setdefault((page["course_code"], page["doc_id"]), []).append(page)
    results = {"page-level (selected)": [], f"fixed-char-{size}": [], f"paragraph-aware-char-{size}": []}
    for document in documents.values():
        joined, starts = "", []
        for page in document:
            content = re.sub(r"[ \t]+", " ", "\n".join(filter(None, [page["native_text"], page["ocr_extracted_text"]]))).strip()
            starts.append(len(joined))
            joined += content + "\n"
        for name, spans in ((f"fixed-char-{size}", _fixed_spans(joined, size)),
                            (f"paragraph-aware-char-{size}", _paragraph_spans(joined, size))):
            for begin, end in spans:
                if not joined[begin:end].strip():
                    continue
                cut = end < len(joined) and joined[end - 1].isalnum() and joined[end].isalnum()
                single = bisect.bisect_right(starts, begin) == bisect.bisect_right(starts, end - 1)
                results[name].append({"chars": end - begin, "cut": cut, "single": single})
        results["page-level (selected)"].extend({"chars": len(page["verbatim_text_span"]), "cut": False, "single": True}
                                                for page in document if page["verbatim_text_span"])
    rows = []
    for name, chunks in results.items():
        rows.append({
            "approach": name, "chunks": len(chunks),
            "median_chars": int(statistics.median(c["chars"] for c in chunks)),
            "max_chars": max(c["chars"] for c in chunks),
            "ends_mid_word": sum(c["cut"] for c in chunks),
            "spans_multiple_pages": sum(not c["single"] for c in chunks),
            "records_a_page_reference": len(chunks) if name.startswith("page-level") else 0,
        })
    return rows


def compare_ocr(pages: list[dict]) -> list[dict]:
    """Same pages with and without the OCR field; native text is extracted independently of OCR."""
    def words(text: str) -> int:
        return len(text.split())

    native = [words(page["native_text"]) for page in pages]
    union = [words(page["verbatim_text_span"]) for page in pages]
    return [{"approach": name, "pages": len(values), "total_words": sum(values),
             "pages_with_no_text": sum(value == 0 for value in values),
             "pages_under_4_words": sum(value < 4 for value in values)}
            for name, values in (("native text only", native), ("native + RapidOCR (selected)", union))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=[*KINDS, "all"], default="all")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--ocr-threads", type=int, default=2)
    parser.add_argument("--repeat", action="store_true", help="Run each branch twice and compare the results")
    args = parser.parse_args()
    for kind in KINDS if args.kind == "all" else (args.kind,):
        options = {"workers": args.workers, "ocr_threads": args.ocr_threads}
        first = execute_pipeline(kind, **options)
        print(f"{kind}: {first['inspection']['pages']} pages -> {first['validation']['outputs']} "
              f"({first['runtime']['seconds']} s)")
        if args.repeat:
            checks = compare_runs(first, execute_pipeline(kind, **options))
            print(f"{kind}: repeatability {checks}")
            if not checks["passed"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
