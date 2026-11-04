"""Week 3 stage contracts on synthetic PDFs; OCR is disabled so these run without models."""
from __future__ import annotations

import json

import pymupdf as fitz
import pytest

from src.week3_pipeline import (
    COURSE_KIND,
    PipelineStageError,
    _paragraph_spans,
    build_lineage_manifest,
    compare_chunking,
    compare_runs,
    execute_pipeline,
    extract_courses,
    verify_manifest,
)

OPTIONS = {"enable_ocr": False, "workers": 1, "ocr_threads": 1}
BODY = "This synthetic course page explains supervised learning models and how they are evaluated in practice."


def make_pdf(path, pages=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    for number in range(pages):
        document.new_page().insert_text((72, 72), f"{BODY} Page {number + 1}.", fontsize=8)
    document.save(path)
    document.close()


@pytest.fixture
def project(tmp_path):
    make_pdf(tmp_path / "data/courses/SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/deck.pdf")
    return tmp_path


def test_records_keep_page_and_source_identity_with_relative_paths(project):
    record = execute_pipeline(COURSE_KIND, project, **OPTIONS)
    lines = (project / record["outputs"][0]).read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert [row["page"] for row in rows] == [1, 2]
    assert {row["source_sha256"] for row in rows} == {record["sources"][0]["sha256"]}
    assert not str(project) in json.dumps(record)


def test_empty_categories_are_reported_as_known_gaps(project):
    gaps = extract_courses(project, **OPTIONS).known_gaps
    assert {"course_code": "SAIA2113", "evidence_level": "CLO", "status": "folder_empty_or_missing"} in gaps


def test_rerun_matches_and_a_changed_source_is_detected(project):
    first = execute_pipeline(COURSE_KIND, project, **OPTIONS)
    assert compare_runs(first, execute_pipeline(COURSE_KIND, project, **OPTIONS))["passed"]
    make_pdf(project / "data/courses/SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/deck.pdf", pages=3)
    assert not compare_runs(first, execute_pipeline(COURSE_KIND, project, **OPTIONS))["passed"]


def test_unreadable_source_stops_at_ingest(project):
    broken = project / "data/courses/SAIA2113_Machine_Learning/03_Assessments_Assessed/broken.pdf"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"not a pdf")
    with pytest.raises(PipelineStageError) as error:
        extract_courses(project, **OPTIONS)
    assert error.value.stage == "ingest"


def test_truncated_sources_stop_at_ingest(project):
    # PDF repair can open a truncated file with blank pages, so opening it is not enough.
    deck = project / "data/courses/SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/deck.pdf"
    make_pdf(deck, pages=20)
    deck.write_bytes(deck.read_bytes()[:-4096])
    with pytest.raises(PipelineStageError, match="no PDF end marker") as error:
        extract_courses(project, **OPTIONS)
    assert error.value.stage == "ingest"
    deck.unlink()
    (deck.parent / "slides.pptx").write_bytes(b"PK\x03\x04 truncated")
    with pytest.raises(PipelineStageError, match="not a complete Office archive"):
        extract_courses(project, **OPTIONS)


def test_missing_sources_stop_at_ingest(tmp_path):
    with pytest.raises(PipelineStageError) as error:
        extract_courses(tmp_path, **OPTIONS)
    assert error.value.stage == "ingest"


def test_manifest_verification_detects_a_changed_output(project):
    extraction = extract_courses(project, **OPTIONS)
    manifest_path = project / "data/week3_manifest.json"
    build_lineage_manifest([extraction], project / "data/processed", manifest_path, project)
    assert verify_manifest(manifest_path, project) == 1
    with (project / "data/processed/prepared_text.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(PipelineStageError, match="Checksum mismatch"):
        verify_manifest(manifest_path, project)


def test_paragraph_spans_match_the_lab_splitter_rules():
    first, second = "a" * 300, "b" * 300
    text = f"{first}\n\n{second}\n\nshort"
    assert [text[a:b] for a, b in _paragraph_spans(text, 500)] == [first, f"{second}\n\nshort"]
    assert len(_paragraph_spans("x" * 1200, 500)) == 3


def test_chunking_comparison_flags_pages_crossed_by_fixed_chunks():
    pages = [{"course_code": "SAIA2113", "doc_id": "d.pdf", "native_text": f"{BODY * 4} {n}", "ocr_extracted_text": "",
              "verbatim_text_span": f"{BODY * 4} {n}"} for n in range(3)]
    rows = {row["approach"]: row for row in compare_chunking(pages)}
    assert rows["page-level (selected)"]["spans_multiple_pages"] == 0
    assert rows["page-level (selected)"]["records_a_page_reference"] == 3
    assert rows["fixed-char-500"]["spans_multiple_pages"] > 0
    assert rows["fixed-char-500"]["records_a_page_reference"] == 0
