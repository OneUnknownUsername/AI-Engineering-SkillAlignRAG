from __future__ import annotations

import io
import os
import hashlib
from dataclasses import asdict

import pymupdf as fitz
import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.build_indexes import Retriever, build, catalog_overlap
from src.common import COURSES, LEVELS, fingerprint, read_json, write_json
from src.extraction import ExtractionConfig, PDFExtractor, clean, covered_area, mask_native_words, unique_lines
from src.pipeline_a_course_ingestion import aspect_card, explicit_clo_statement, ingest, skip_reason
from src.pipeline_b_indsf_skills import compile_benchmark, verify_benchmark
from src.indsf_extraction import extract_all_skills
from src.run_retrieval_smoke_test import hit_description, level_status, run
from src.step0_normalize_formats import normalize_formats
from src.validate_artifacts import validate


def make_pdf(path, texts):
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        for text in texts:
            doc.new_page().insert_textbox(fitz.Rect(30, 30, 560, 780), text)
        doc.save(path)


def locked_skills():
    return [{"skill_id": f"S{i:02d}", "skill_name": f"Synthetic process {i}",
             "bucket": "A" if i < 4 else "B" if i < 8 else "C" if i < 11 else "D",
             "sfia_codes": ["DATS"], "retrieval_query": "clean missing data values",
             "nli_hypothesis_template": "The course explains how to clean missing data values.",
             "indsf_provenance": [{"doc_id": "test.pdf", "pdf_page_no": 1,
                                   "role_title": "Data Analyst", "matched_source_excerpt": "clean missing data"}]}
            for i in range(1, 13)]


class ConstantEncoder:
    """Keep non-retrieval integration tests independent of downloaded models."""
    def encode(self, texts, **kwargs):
        return np.tile([1., 0.], (len(texts), 1))


def benchmark_pages():
    return [{"doc_id": "test.pdf", "pdf_page_no": 1,
             "native_text": "Data Analyst\nJOB DESCRIPTION\nCollect and clean missing data carefully.",
             "verbatim_text_span": "Data Analyst JOB DESCRIPTION Collect and clean missing data carefully."}]


def test_pii_and_boilerplate_do_not_leak():
    text, events = clean("Contact alice.test@utm.my +6012-3456789 012 34567890 Office: N28-403\n"
                         "www.fai.utm.my Innovating Solutions\nEvaluate model performance")
    assert "alice" not in text and "3456789" not in text and "N28" not in text
    assert "Evaluate model performance" in text and "utm.my" not in text
    assert {e["kind"] for e in events} == {"email", "phone", "office_room"}
    assert all(set(e) == {"kind", "offset"} for e in events)


def test_letter_spaced_contact_pii():
    text, events = clean("W h a t s a p p : 0 1 2 3 4 5 6 7 8 9\n"
                         "E m a i l : a l i c e @ e x a m p l e . c o m\n"
                         "R o o m : A B 1 2 3 ( L e v e l 6 )")
    assert {e["kind"] for e in events} == {"phone", "email", "office_room"}
    assert "alice" not in text and "AB123" not in text and "0123456789" not in text
    assert clean("Room: MJIIT 060601 (Level 6)")[0] == "[REDACTED_PII] (Level 6)"


def test_room_redaction_requires_explicit_office_identifiers():
    ordinary = "Booking.com: 1 room\n1 nights, 2 adults. Room size 22 square metres. Office 365."
    assert clean(ordinary) == (ordinary, [])
    for private in ["Room: N28-403", "Room # AB-123", "Office: N28-403", "MJIIT 060601", "Bilik: 412"]:
        redacted, events = clean(private)
        assert redacted == "[REDACTED_PII]" and events[0]["kind"] == "office_room"


def test_ci_force_ocr_and_tables_on_every_dense_native_page(tmp_path, monkeypatch):
    import pdfplumber.page
    pdf = tmp_path / "ci.pdf"
    make_pdf(pdf, ["Native curriculum content explains teaching objectives and assessment methods. " * 8] * 2)
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False), tmp_path / "cache")
    images, tables = [], []
    def recognize(array):
        images.append(array)
        return ([[[], "CLO2: Construct data transformation methods.", .99]], None)
    extractor.ocr = recognize
    original = pdfplumber.page.Page.extract_tables
    def track_tables(page, *args, **kwargs):
        tables.append(page.page_number)
        return original(page, *args, **kwargs)
    monkeypatch.setattr(pdfplumber.page.Page, "extract_tables", track_tables)
    regular = list(extractor.extract(pdf))
    assert all(p["ocr_status"] == "not_needed" for p in regular) and not images
    forced = list(extractor.extract(pdf, force_ocr=True))
    assert len(images) == 2 and tables == [1, 2, 1, 2]
    assert all(p["ocr_forced"] and p["ocr_status"] == "completed" and not p["ocr_native_word_masking"] for p in forced)
    assert all("Construct data transformation" in p["verbatim_text_span"] for p in forced)
    assert all(array.min() < 255 for array in images)


def test_legacy_cache_reparses_room_redactions_to_restore_source_text(tmp_path, monkeypatch):
    pdf = tmp_path / "booking.pdf"
    make_pdf(pdf, ["Booking options: 1 room for 2 adults.", "An unaffected second page."])
    config = ExtractionConfig(enable_ocr=False)
    extractor = PDFExtractor(config, tmp_path / "cache")
    legacy = list(extractor._extract(pdf))
    legacy[0]["native_text"] = "Booking options: 1 [REDACTED_PII] adults."
    legacy[0]["verbatim_text_span"] = legacy[0]["native_text"]
    legacy[0]["redaction_events"] = [{"kind": "office_room", "offset": 19}]
    settings = asdict(config)
    settings.pop("ocr_threads")
    key = fingerprint({"source_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                       "config": settings, "extractor_revision": 2})
    write_json(tmp_path / "cache" / (key + ".json"), legacy)
    calls = []
    original = extractor._extract
    def tracking(path, **kwargs):
        calls.append(kwargs)
        yield from original(path, **kwargs)
    monkeypatch.setattr(extractor, "_extract", tracking)
    restored = list(extractor.extract(pdf))
    assert "1 room for 2 adults" in restored[0]["verbatim_text_span"]
    assert calls == [{"force_ocr": False, "page_numbers": {1}}]
    assert restored[0]["redaction_events"] == []


def test_ocr_dedup_and_noise():
    assert unique_lines("Native words\nNew image text\nNew image text", "Native words") == "New image text"
    assert unique_lines("AI", "Fairness principles") == "AI"
    seen = set()
    assert skip_reason("THANK YOU 9", seen)
    assert skip_reason("CLASS ACTIVITY: What is Artificial Intelligence?", seen)
    assert skip_reason("Agenda: data preparation and cleaning missing values", seen) is None
    assert skip_reason("Agenda: data preparation and cleaning missing values", seen) == "duplicate_agenda"
    assert skip_reason("", set(), has_visual_content=True) is None
    assert skip_reason("THANK YOU", set(), has_visual_content=True) == "divider"


def test_native_ocr_vision_separation(tmp_path, monkeypatch):
    path = tmp_path / "visual.pdf"
    image = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(image).text((20, 20), "Diagram workflow", fill="black")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=500, height=500)
        page.insert_text((20, 25), "Native diagram")
        page.insert_image(fitz.Rect(20, 50, 470, 490), stream=stream.getvalue())
        doc.save(path)
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False, enable_vision_llm=True))
    extractor.ocr = lambda array: ([[[], "Native diagram", .99], [[], "Image-only steps", .99]], None)
    monkeypatch.setattr(extractor, "vision", lambda png: ("Generated workflow relationships.", None))
    result = list(extractor.extract(path))[0]
    assert result["ocr_extracted_text"] == "Image-only steps"
    assert result["visual_diagram_summary"] == "Generated workflow relationships."
    assert "Generated" not in result["verbatim_text_span"]
    assert set(result["extraction_methods_used"]) == {"native_text", "rapidocr", "ollama_vision"}
    assert result["pdf_page_no"] == 1


def test_local_vision_endpoint_and_graceful_unavailable(monkeypatch):
    with pytest.raises(ValueError, match="local HTTP"):
        PDFExtractor(ExtractionConfig(enable_ocr=False, ollama_url="https://example.com/api/generate"))
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False))
    class Offline:
        def open(self, *args, **kwargs):
            raise OSError("offline")
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Offline())
    summary, error = extractor.vision(b"test")
    assert summary == "" and "unavailable" in error


def test_overlapping_images_not_double_counted():
    assert covered_area([fitz.Rect(0, 0, 100, 100), fitz.Rect(50, 0, 150, 100)]) == 15000


def test_ocr_mask_removes_only_known_native_word_regions():
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.insert_text((20, 30), "Known native text")
        page.draw_rect(fitz.Rect(100, 100, 200, 200), color=(0, 0, 1), fill=(0, 0, 1))
        png = page.get_pixmap(dpi=72, alpha=False).tobytes("png")
        masked = np.array(Image.open(io.BytesIO(mask_native_words(png, page, 72))))
        assert masked[15:35, 15:115].min() == 255
        assert tuple(masked[150, 150]) == (0, 0, 255)


def test_document_cache_is_sanitized_and_invalidates_changed_sources(tmp_path, monkeypatch):
    pdf = tmp_path / "cached.pdf"
    make_pdf(pdf, ["Contact alice@example.com about cleaning missing values."])
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False), tmp_path / "cache")
    calls = []
    original = extractor._extract
    def counting_extract(path):
        calls.append(path)
        yield from original(path)
    monkeypatch.setattr(extractor, "_extract", counting_extract)
    first = list(extractor.extract(pdf))
    assert list(extractor.extract(pdf)) == first and len(calls) == 1
    cached_file = next((tmp_path / "cache").glob("*.json"))
    assert "alice@example.com" not in cached_file.read_text()
    legacy = read_json(cached_file)
    legacy[0]["ocr_extracted_text"] = "Room: MJIIT 060601"
    write_json(cached_file, legacy)
    assert list(extractor.extract(pdf))[0]["ocr_extracted_text"] == "[REDACTED_PII]"
    assert "060601" not in cached_file.read_text()
    make_pdf(pdf, ["Changed source content describing model evaluation."])
    assert list(extractor.extract(pdf)) != first and len(calls) == 2


def test_normalization_stale_source_not_parsed_as_current(tmp_path, monkeypatch):
    data, output = tmp_path / "data", tmp_path / "outputs"
    source = data / "courses/SAIA1013/02_Lecture_Slides_Taught/deck.pptx"
    source.parent.mkdir(parents=True)
    make_pdf(source.with_suffix(".pdf"), ["Old stale slide text"])
    source.write_bytes(b"unconverted")
    newer = source.with_suffix(".pdf").stat().st_mtime_ns + 1_000_000_000
    os.utime(source, ns=(newer, newer))
    monkeypatch.setattr("src.step0_normalize_formats.find_soffice", lambda: None)
    def unavailable(*args):
        raise RuntimeError("Office unavailable")
    monkeypatch.setattr("src.step0_normalize_formats.office_convert", unavailable)
    records = normalize_formats(data, output)
    assert len(records) == 1
    assert records[0]["status"] == "conversion_failed"


def test_office_conversion_preserves_original_format_and_reuses_pdf(tmp_path, monkeypatch):
    data, output = tmp_path / "data", tmp_path / "outputs"
    source = data / "courses/SAIA1013/02_Lecture_Slides_Taught/deck.pptx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic office input")
    calls = []
    monkeypatch.setattr("src.step0_normalize_formats.find_soffice", lambda: None)
    def convert(original, destination):
        calls.append(original)
        make_pdf(destination, ["Explain how to perform data cleaning."])
    monkeypatch.setattr("src.step0_normalize_formats.office_convert", convert)
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False))
    ingest(data, output, extractor)
    chunk = read_json(output / "parsed_course_chunks.json")[0]
    assert chunk["original_format"] == "pptx" and chunk["pdf_page_no"] == 1
    normalize_formats(data, output)
    assert len(calls) == 1 and source.read_bytes() == b"synthetic office input"


def test_automated_provenance_is_source_verified():
    skills = locked_skills()
    pages = benchmark_pages()
    compiled = compile_benchmark(skills, pages, encoder=ConstantEncoder())
    assert all(s["provenance_verified"] for s in compiled)
    verify_benchmark(compiled, pages)
    compiled[0]["indsf_provenance"][0]["matched_source_excerpt"] = "Invented paraphrase"
    with pytest.raises(ValueError, match="differs"):
        verify_benchmark(compiled, pages)


def test_compilation_preserves_definitions_and_ignores_supplied_citations():
    skills = locked_skills()
    skills[7]["sfia_codes"] = ["ETHICS"]
    skills[0]["indsf_provenance"][0]["matched_source_excerpt"] = "Invented source"
    compiled = compile_benchmark(skills, benchmark_pages(), encoder=ConstantEncoder())
    assert compiled[0]["indsf_provenance"][0]["matched_source_excerpt"] == "Collect and clean missing data carefully."
    assert "provided_indsf_provenance" not in compiled[0]
    assert compiled[7]["sfia_codes"] == ["ETHICS"]
    assert compiled[0]["skill_name"] == skills[0]["skill_name"]


def test_parallel_ingestion_preserves_all_pages(tmp_path):
    data, output = tmp_path / "data", tmp_path / "outputs"
    make_pdf(data / "courses/SAIA2143_Test/01_CI_CLO/ci.pdf", ["Explain how to clean missing data values."])
    make_pdf(data / "courses/SAIA2143_Test/03_Assessments_Assessed/task.pdf", ["Submit an analysis of data quality errors."])
    result = ingest(data, output, PDFExtractor(ExtractionConfig(enable_ocr=False)), workers=2)
    assert result["courses"]["SAIA2143"]["level_availability"] == {"CLO": True, "Taught": False, "Assessed": True}
    assert len(read_json(output / "parsed_course_chunks.json")) == 2


def test_aspect_cards_detect_embedded_evidence():
    pages = [{"native_text": "Data preparation\nTopic learning\noutcomes\nHandle missing values",
              "ocr_extracted_text": "", "pdf_page_no": 1,
              "verbatim_text_span": "CLO1: Clean data. Assignment (5%) submit analysis."}]
    card = aspect_card("test.pdf", pages)
    assert "Handle missing values" in card["declared_learning_outcomes_or_agenda"]
    assert card["embedded_clo_pages"] == [1] and card["embedded_assessment_pages"] == [1]
    assert catalog_overlap("Handle missing values", card) > 0
    pages[0]["native_text"] = "Bab Adab\nPelajar akan dapat:\nMenganalisis dilema moral dalam AI moden"
    assert "Menganalisis dilema moral dalam AI moden" in aspect_card("malay.pdf", pages)["declared_learning_outcomes_or_agenda"]


@pytest.mark.parametrize("heading", ["Learning Outcome", "At the end of this lesson:", "MEETING 4 OVERVIEW",
                                     "COURSE OVERVIEW", "Outline", "Topic 12:"])
def test_catalog_scans_through_page_six_and_strips_footer(heading):
    pages = [{"pdf_page_no": n, "native_text": "A cover page", "ocr_extracted_text": "", "verbatim_text_span": "A cover page"}
             for n in range(1, 8)]
    pages[5]["native_text"] = heading + "\nExplain model validation\nFaculty of\nArtificial Intelligence\nUNIVERSITI TEKNOLOGI MALAYSIA\n6"
    pages[6]["native_text"] = "Outline\nThis seventh-page item must not enter the card"
    card = aspect_card("deck.pdf", pages)
    assert "Explain model validation" in card["declared_learning_outcomes_or_agenda"]
    assert all(not any(footer in item for footer in ["Faculty of", "Artificial Intelligence", "UNIVERSITI", "seventh-page"])
               for item in card["declared_learning_outcomes_or_agenda"])
    assert card["outcome_source_pages"] == [6] and card["aspect_scan_pdf_pages"] == list(range(1, 7))


def test_auxiliary_clo_routes_preserve_source_and_empty_folder_abstention(tmp_path):
    data, output = tmp_path / "data", tmp_path / "outputs"
    make_pdf(data / "courses/SAIA1013_Test/01_CI_CLO/ci.pdf", ["Course Information and intended learning objectives."])
    make_pdf(data / "courses/SAIA1013_Test/02_Lecture_Slides_Taught/deck.pdf", [
        "CLO1: Explain methods to clean missing data values.", "This activity addresses CLO3 and requires a written report."])
    make_pdf(data / "courses/SAIA1013_Test/03_Assessments_Assessed/exam.pdf", [
        "Course Learning Outcome 2: Construct data transformations and clean missing values."])
    make_pdf(data / "courses/SAIA2113_Test/02_Lecture_Slides_Taught/deck.pdf", [
        "CLO2: Explain how to clean missing data values."])
    catalog = ingest(data, output, PDFExtractor(ExtractionConfig(enable_ocr=False)))
    chunks = read_json(output / "parsed_course_chunks.json")
    assert len(chunks) == len(read_json(output / "verbatim_lookup_store.json")) == 5
    auxiliary = [c for c in chunks if c["auxiliary_evidence_levels"]]
    assert {c["evidence_level"] for c in auxiliary} == {"Taught", "Assessed"} and len(auxiliary) == 2
    assert len(catalog["courses"]["SAIA1013"]["auxiliary_clo_pages"]) == 2
    assert not catalog["courses"]["SAIA2113"]["level_availability"]["CLO"]
    assert not explicit_clo_statement("This activity addresses CLO3 and requires a report.")
    build(output, lexical_only=True)
    retriever = Retriever(output)
    clo = retriever.retrieve("SAIA1013", "clean missing data", "CLO")
    assert {h["source_evidence_level"] for h in clo} == {"Taught", "Assessed"}
    assert all(h["evidence_level"] == "CLO" and h["is_auxiliary_evidence"] for h in clo)
    assert retriever.retrieve("SAIA2113", "clean missing data", "CLO") == []
    assert len(retriever.manifest["partitions"]["pooled"]["SAIA1013"]) == 4


@pytest.fixture
def indexed(tmp_path):
    data, output = tmp_path / "data", tmp_path / "outputs"
    make_pdf(data / "courses/SAIA1013_Responsible_AI/02_Lecture_Slides_Taught/deck.pdf", [
        "Data preparation\nAgenda: clean missing data values and explain their causes.",
        "THANK YOU",
        "Cleaning missing data values requires identifying nulls then choosing an imputation method."
    ])
    make_pdf(data / "courses/SAIA1013_Responsible_AI/01_CI_CLO/ci.pdf", [
        "CLO1: Explain how to clean missing data values and evaluate imputation methods."
    ])
    catalog = ingest(data, output, PDFExtractor(ExtractionConfig(enable_ocr=False)))
    assert catalog["courses"]["SAIA1013"]["level_availability"] == {"CLO": True, "Taught": True, "Assessed": False}
    assert not any(catalog["courses"]["SAIA2113"]["level_availability"].values())
    chunks = read_json(output / "parsed_course_chunks.json")
    assert len(chunks) == 4 and sum(c["indexable"] for c in chunks) == 3
    assert len(read_json(output / "verbatim_lookup_store.json")) == 4
    build(output, lexical_only=True)
    return output


def test_routing_pooling_missing_levels_and_all_36_queries(indexed):
    retriever = Retriever(indexed)
    assert all(h["evidence_level"] == "CLO" for h in retriever.retrieve("SAIA1013", "clean missing data", "CLO"))
    assert {h["evidence_level"] for h in retriever.retrieve("SAIA1013", "clean missing data")} == {"CLO", "Taught"}
    assert retriever.retrieve("SAIA1013", "clean missing data", "Assessed") == []
    assert retriever.retrieve("SAIA1013", "quuxunknownword", "Taught") == []
    raw = benchmark_pages()
    skills = compile_benchmark(locked_skills(), raw, encoder=ConstantEncoder())
    write_json(indexed / "industry_skills_benchmark.json", skills)
    write_json(indexed / "indsf_raw_extracted.json", raw)
    write_json(indexed / "indsf_all_extracted_skills.json", extract_all_skills(raw))
    logs = run(indexed)
    assert len(logs) == 36
    assert logs[0]["routed"]["Assessed"]["status"] == "INSUFFICIENT_EVIDENCE (Folder Empty)"
    assert "lexical_only_diagnostic" in (indexed / "retrieval_smoke_test_report.md").read_text()


def test_stale_index_is_rejected(indexed):
    chunks = read_json(indexed / "parsed_course_chunks.json")
    chunks[0]["verbatim_text_span"] = "changed"
    write_json(indexed / "parsed_course_chunks.json", chunks)
    with pytest.raises(ValueError, match="stale"):
        Retriever(indexed)


def test_failed_processing_is_not_empty_folder():
    course = {"level_availability": {"CLO": False}, "level_status": {"CLO": "processing_failed"}}
    assert level_status(course, "CLO", []) == "INSUFFICIENT_EVIDENCE (Document Processing Failed)"


def test_visual_only_candidate_never_claims_a_verbatim_quote(tmp_path, monkeypatch):
    data, output = tmp_path / "data", tmp_path / "outputs"
    pdf = data / "courses/SAIA1013_Test/02_Lecture_Slides_Taught/diagram.pdf"
    pdf.parent.mkdir(parents=True)
    image = Image.new("RGB", (300, 300), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 200, 200), outline="blue", width=4)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    with fitz.open() as document:
        document.new_page(width=300, height=300).insert_image(fitz.Rect(0, 0, 300, 300), stream=stream.getvalue())
        document.save(pdf)
    extractor = PDFExtractor(ExtractionConfig(enable_ocr=False, enable_vision_llm=True))
    monkeypatch.setattr(extractor, "vision", lambda png: ("The diagram shows workflow components.", None))
    ingest(data, output, extractor)
    chunk = read_json(output / "parsed_course_chunks.json")[0]
    assert chunk["indexable"] and chunk["verbatim_text_span"] == ""
    build(output, lexical_only=True)
    skills = locked_skills()
    for skill in skills:
        skill["retrieval_query"] = "workflow components"
    raw = benchmark_pages()
    write_json(output / "indsf_raw_extracted.json", raw)
    write_json(output / "indsf_all_extracted_skills.json", extract_all_skills(raw))
    write_json(output / "industry_skills_benchmark.json", compile_benchmark(skills, raw, encoder=ConstantEncoder()))
    logs = run(output)
    hit = logs[0]["routed"]["Taught"]["hits"][0]
    assert hit["snippet"] == "" and hit["verbatim_verification"] == "no_verbatim_text"
    assert "generated, not a quote" in hit_description([hit])
    assert validate(output)["status"] == "passed"
