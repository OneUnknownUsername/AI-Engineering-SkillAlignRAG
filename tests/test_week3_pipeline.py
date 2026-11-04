"""Week 3 stage contracts on synthetic PDFs; OCR is disabled so these run without models."""
from __future__ import annotations

import json

import pymupdf as fitz
import pytest

from src.week3_pipeline import (
    COURSE_KIND,
    PipelineStageError,
    INDSF_KIND,
    OWNERS,
    Extraction,
    _paragraph_spans,
    blank_line_breaks,
    build_lineage_manifest,
    compare_chunking,
    compare_runs,
    execute_pipeline,
    extract_courses,
    sha256_file,
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


def comparison_input(raw_pages):
    key = ("SAIA2113", "d.pdf")
    pages = [{"course_code": key[0], "doc_id": key[1], "pdf_page_no": number, "ocr_extracted_text": "",
              "verbatim_text_span": " ".join(raw.split())} for number, raw in enumerate(raw_pages, 1)]
    return pages, {key: raw_pages}


def test_chunking_comparison_flags_pages_crossed_by_fixed_chunks():
    rows = {row["approach"]: row for row in compare_chunking(*comparison_input([f"{BODY * 4} {n}" for n in range(3)]))}
    assert rows["page-level (selected)"]["spans_multiple_pages"] == 0
    assert rows["page-level (selected)"]["records_a_page_reference"] == 3
    assert rows["fixed-char-500"]["spans_multiple_pages"] > 0
    assert rows["fixed-char-500"]["records_a_page_reference"] == 0


def test_paragraph_splitter_receives_blank_lines_from_raw_text():
    # The raw text keeps its paragraphs even when the prepared record has been flattened.
    paragraphs = "\n\n".join(["a" * 300, "b" * 300, "c" * 300])
    rows = {row["approach"]: row for row in compare_chunking(*comparison_input([paragraphs]))}
    assert rows["fixed-char-500"]["ends_mid_word"] > 0
    assert rows["paragraph-aware-char-500"]["ends_mid_word"] == 0


def test_blank_line_breaks_separate_paragraphs_from_page_boundaries():
    counts = blank_line_breaks({("c", "d"): ["one\n\ntwo\n", "three\n"]})
    assert counts == {"inside_a_page": 1, "pages_with_a_break_inside": 1, "page_boundaries": 1, "pages": 2}


def indsf_extraction(root):
    doc_ids = ("a.pdf", "b.pdf")
    paths = [f"data/industry_benchmark/{doc_id}" for doc_id in doc_ids]
    hashes = {}
    for path in paths:
        make_pdf(root / path)
        hashes[path] = sha256_file(root / path)
    sources = [{"path": path, "sha256": hashes[path], "format": "pdf", "normalized_pdf_sha256": None, "course_code": None,
                "evidence_level": "Industry benchmark", "pages": 1, "records": 1} for path in paths]
    pages = [{"record_id": doc_id, "text": BODY, "source": path, "source_sha256": hashes[path], "page": 1}
             for doc_id, path in zip(doc_ids, paths)]
    items = [{"item_id": str(n), "doc_id": doc_id, "pdf_page_no": 1, "verbatim_text": BODY}
             for n, doc_id in enumerate(("a.pdf", "a.pdf", "b.pdf"))]
    return Extraction(INDSF_KIND, sources, {"prepared_indsf_text.jsonl": pages, "prepared_indsf_items.jsonl": items}, {}, "method")


def test_lineage_links_each_source_to_every_prepared_output(tmp_path):
    manifest = build_lineage_manifest([indsf_extraction(tmp_path)], tmp_path / "data/processed", tmp_path / "data/week3_manifest.json", tmp_path)
    links = {(r["source_id"], r["prepared_output"].rsplit("/", 1)[1]): r["records"] for r in manifest["records"]}
    assert links == {("SRC01", "prepared_indsf_text.jsonl"): 1, ("SRC02", "prepared_indsf_text.jsonl"): 1,
                     ("SRC01", "prepared_indsf_items.jsonl"): 2, ("SRC02", "prepared_indsf_items.jsonl"): 1}
    assert all(r["owner"] == OWNERS[INDSF_KIND] for r in manifest["records"])
    assert verify_manifest(tmp_path / "data/week3_manifest.json", tmp_path) == 4
    with (tmp_path / "data/processed/prepared_indsf_items.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(PipelineStageError, match="Checksum mismatch"):
        verify_manifest(tmp_path / "data/week3_manifest.json", tmp_path)


def test_item_without_a_registered_source_stops_at_validate(tmp_path):
    extraction = indsf_extraction(tmp_path)
    extraction.outputs["prepared_indsf_items.jsonl"][0]["doc_id"] = "unknown.pdf"
    with pytest.raises(PipelineStageError, match="does not link to a registered source") as error:
        build_lineage_manifest([extraction], tmp_path / "data/processed", tmp_path / "data/week3_manifest.json", tmp_path)
    assert error.value.stage == "validate"


def test_record_with_empty_text_stops_at_validate(tmp_path):
    extraction = indsf_extraction(tmp_path)
    extraction.outputs["prepared_indsf_items.jsonl"][0]["verbatim_text"] = "  "
    with pytest.raises(PipelineStageError, match="empty text") as error:
        build_lineage_manifest([extraction], tmp_path / "data/processed", tmp_path / "data/week3_manifest.json", tmp_path)
    assert error.value.stage == "validate"


def incomplete_manifest(root, keep):
    path = root / "data/week3_manifest.json"
    build_lineage_manifest([indsf_extraction(root)], root / "data/processed", path, root)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["records"] = [record for record in manifest["records"] if keep(record)]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.mark.parametrize("keep, message", [
    (lambda r: "items" not in r["prepared_output"], "Outputs missing from manifest"),
    (lambda r: r["source_id"] != "SRC02", "Sources missing from manifest"),
    (lambda r: not (r["source_id"] == "SRC02" and "items" in r["prepared_output"]), "Manifest lists 2 records"),
])
def test_incomplete_manifest_stops_at_record_lineage(tmp_path, keep, message):
    with pytest.raises(PipelineStageError, match=message) as error:
        verify_manifest(incomplete_manifest(tmp_path, keep), tmp_path)
    assert error.value.stage == "record_lineage"
