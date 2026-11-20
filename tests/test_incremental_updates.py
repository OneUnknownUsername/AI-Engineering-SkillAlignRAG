"""Phase C (NFR4): updating one course's category rebuilds only that index store, and re-reading one
course gives the same records as reading every course."""
import hashlib
import shutil

import numpy as np
import pytest

from src import build_indexes
from src.build_indexes import Retriever, build, load_embeddings, search_text
from src.common import read_json, write_json
from src.extraction import ExtractionConfig, PDFExtractor
from src.pipeline_a_course_ingestion import ingest
from tests.test_pipeline import make_pdf


class CountingEncoder:
    """A stand-in model: a fixed vector per text, counting how many texts it is asked to encode."""
    def __init__(self):
        self.encoded = 0

    def encode(self, texts, **kwargs):
        self.encoded += len(texts)
        rows = [np.frombuffer(hashlib.sha256(t.encode()).digest()[:16], dtype=np.uint8).astype(np.float32) for t in texts]
        return np.asarray([r / np.linalg.norm(r) for r in rows])


@pytest.fixture
def course_data(tmp_path):
    data, output = tmp_path / "data", tmp_path / "outputs"
    make_pdf(data / "courses/SAIA1013_RAI/01_CI_CLO/ci.pdf", ["CLO1: Explain how to clean missing data values."])
    make_pdf(data / "courses/SAIA1013_RAI/02_Lecture_Slides_Taught/deck.pdf",
             ["Cleaning missing data values requires identifying nulls first.", "Imputation methods replace missing values."])
    make_pdf(data / "courses/SAIA2143_DWV/02_Lecture_Slides_Taught/viz.pdf", ["Charts communicate exploratory data analysis."])
    make_pdf(data / "courses/SAIA2143_DWV/03_Assessments_Assessed/task.pdf", ["Assignment: build a chart of cleaned data."])
    ingest(data, output, PDFExtractor(ExtractionConfig(enable_ocr=False)))
    return data, output


@pytest.fixture
def encoder(monkeypatch):
    model = CountingEncoder()
    monkeypatch.setattr(build_indexes, "load_model", lambda *args, **kwargs: model)
    return model


def store_state(output):
    return {p.relative_to(output).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted((output / "indexes" / "stores").rglob("*")) if p.is_file()}


def test_one_changed_page_rebuilds_only_its_store(course_data, encoder):
    _, output = course_data
    first = build(output)
    assert first["last_build"]["vectors_computed"] == encoder.encoded == 5
    assert len(first["last_build"]["stores_rebuilt"]) == 9  # The first build writes every store.
    before = store_state(output)
    old = load_embeddings(output / "indexes", first, read_json(output / "indexes/chunks.json"))

    chunks = read_json(output / "parsed_course_chunks.json")
    page = next(c for c in chunks if c["doc_id"] == "deck.pdf" and c["pdf_page_no"] == 2)
    page["verbatim_text_span"] = "Imputation methods replace missing values with the median."
    write_json(output / "parsed_course_chunks.json", chunks)
    second = build(output)

    assert second["last_build"]["stores_rebuilt"] == ["SAIA1013::Taught"]
    assert second["last_build"]["vectors_computed"] == 1 and encoder.encoded == 6  # Only the changed text.
    after = store_state(output)
    changed = {path for path in after if after[path] != before.get(path)}
    assert changed == {"indexes/stores/SAIA1013/Taught.npy", "indexes/stores/SAIA1013/Taught.json"}
    new = Retriever(output).embeddings
    unchanged = [i for i, c in enumerate(read_json(output / "indexes/chunks.json")) if c["chunk_id"] != page["chunk_id"]]
    assert np.array_equal(old[unchanged], new[unchanged])


def test_a_rebuild_with_nothing_changed_writes_no_store_and_loads_no_model(course_data, encoder):
    _, output = course_data
    build(output)
    before, encoded = store_state(output), encoder.encoded
    manifest = build(output)
    assert manifest["last_build"]["stores_rebuilt"] == [] and encoder.encoded == encoded
    assert store_state(output) == before


def test_the_old_single_file_index_converts_without_new_vectors(course_data, encoder):
    _, output = course_data
    build(output)
    directory = output / "indexes"
    chunks = read_json(directory / "chunks.json")
    vectors = load_embeddings(directory, read_json(directory / "manifest.json"), chunks)
    # Recreate the earlier layout: one embeddings file, schema 3, no stores.
    shutil.rmtree(directory / "stores")
    np.save(directory / "embeddings.npy", vectors, allow_pickle=False)
    manifest = read_json(directory / "manifest.json")
    manifest.update(schema_version=3, embedding_file="embeddings.npy")
    manifest.pop("stores")
    write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="layout is out of date"):
        Retriever(output)
    encoded = encoder.encoded
    converted = build(output)
    assert converted["last_build"]["vectors_computed"] == 0 and encoder.encoded == encoded
    assert np.array_equal(Retriever(output).embeddings, vectors)
    assert not (directory / "embeddings.npy").exists()


def test_a_changed_store_file_is_refused(course_data, encoder):
    _, output = course_data
    build(output)
    store = output / "indexes/stores/SAIA2143/Taught.npy"
    array = np.load(store)
    array[0, 0] += 1
    np.save(store, array, allow_pickle=False)
    with pytest.raises(ValueError, match="do not match"):
        Retriever(output)


def test_re_reading_one_course_matches_reading_all(course_data, tmp_path):
    data, output = course_data
    make_pdf(data / "courses/SAIA2143_DWV/02_Lecture_Slides_Taught/new.pdf", ["Box plots reveal outliers in cleaned data."])
    full, scoped = tmp_path / "full", tmp_path / "scoped"
    shutil.copytree(output, full)
    shutil.copytree(output, scoped)
    ingest(data, full, PDFExtractor(ExtractionConfig(enable_ocr=False)))
    ingest(data, scoped, PDFExtractor(ExtractionConfig(enable_ocr=False)), courses=["SAIA2143"])
    for name in ("course_catalog_manifest.json", "parsed_course_chunks.json", "verbatim_lookup_store.json",
                 "course_ingestion_events.json"):
        assert read_json(full / name) == read_json(scoped / name), name
    assert any(c["doc_id"] == "new.pdf" for c in read_json(scoped / "parsed_course_chunks.json"))


def test_re_reading_one_course_needs_a_full_reading_first(tmp_path):
    with pytest.raises(ValueError, match="full ingestion first"):
        ingest(tmp_path / "data", tmp_path / "outputs", PDFExtractor(ExtractionConfig(enable_ocr=False)), courses=["SAIA2143"])
    with pytest.raises(ValueError, match="Unsupported course"):
        ingest(tmp_path / "data", tmp_path / "outputs", PDFExtractor(ExtractionConfig(enable_ocr=False)), courses=["SAIA9999"])
