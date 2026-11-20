"""Persist dense embeddings and routed/pooled BM25 corpus partitions.

Embeddings are kept in one store per course and evidence level (stores/<course>/<level>.npy with
its page list in .json). A rebuild rewrites only the stores whose pages changed and computes
vectors only for new or changed page text, reusing the rest (NFR4), so updating one course's
category leaves every other store's files untouched.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from time import perf_counter

import numpy as np
from rank_bm25 import BM25Plus

from src.curriculum_scope import clo_evidence_window, has_official_commitment, mark_slide_clo_pages, explicit_clo_statement
from src.common import COURSES, LEVELS, base_parser, evidence_levels, fingerprint, read_json, tokens, write_json

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
STOPWORDS = set("a an the and or to of in on for with by is are be as how this that from at it its".split())  # Used by BM25 and Pipeline B.
LEXICAL_TOKENIZER = "lowercase_alnum_without_stopwords_v1"
FUSION = "reciprocal_rank_fusion"
ROUTING_POLICY = "ci_only_clo_v3"  # The CI alone feeds the CLO route (FR3).
RRF_K0 = 60  # Smoothing constant from Cormack, Clarke and Buttcher (2009); not tuned on course data.
INDEX_SCHEMA = 4  # One embedding store per course and evidence level.


def search_text(chunk: dict) -> str:
    text = chunk["verbatim_text_span"]
    if has_official_commitment(chunk):
        # Rank on the commitment, rather than staff metadata and duplicate OCR prefixes.
        text = clo_evidence_window(text)[:3000]
    return "\n".join(filter(None, [text, chunk.get("visual_diagram_summary", "")]))


def lexical_terms(text: str) -> list[str]:
    """BM25 terms: function words are dropped so they cannot make a page count as a keyword match."""
    return [t for t in tokens(text) if t not in STOPWORDS]


def ranking(scores: np.ndarray) -> dict[int, int]:
    """1-based rank of each row the retriever matched; unmatched rows (score 0) are unranked."""
    order = sorted((j for j in range(len(scores)) if scores[j] > 0), key=lambda j: -scores[j])
    return {j: rank for rank, j in enumerate(order, 1)}


def reciprocal_rank_fusion(rankings: list[dict[int, int]], size: int, k0: int = RRF_K0) -> np.ndarray:
    """Score each row by the sum of 1 / (k0 + rank) over the retrievers that ranked it."""
    fused = np.zeros(size)
    for ranks in rankings:
        for j, rank in ranks.items():
            fused[j] += 1 / (k0 + rank)
    return fused


def load_model(model: str, directory: Path, offline: bool):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model, cache_folder=str(directory), local_files_only=offline, device="cpu")


def text_sha(chunk: dict) -> str:
    return hashlib.sha256(search_text(chunk).encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def store_files(directory: Path, course: str, level: str) -> tuple[Path, Path]:
    base = directory / "stores" / course / level
    return base.with_suffix(".npy"), base.with_suffix(".json")


def previous_vectors(directory: Path, model: str | None) -> dict[str, np.ndarray]:
    """Vectors from the last build, by page-text hash, so unchanged text is never encoded again.
    Also reads the earlier single-file layout, so converting to stores reuses its vectors exactly."""
    manifest_path = directory / "manifest.json"
    if model is None or not manifest_path.exists():
        return {}
    manifest = read_json(manifest_path)
    if manifest.get("model") != model:
        return {}
    vectors = {}
    if manifest.get("schema_version", 0) >= INDEX_SCHEMA:
        for store in manifest.get("stores", {}).values():
            array_path, meta_path = directory / store["file"], directory / store["meta"]
            if array_path.exists() and meta_path.exists() and file_sha(array_path) == store["sha256"]:
                array = np.load(array_path, allow_pickle=False)
                vectors.update(zip(read_json(meta_path)["text_sha256"], array))
    elif (directory / "embeddings.npy").exists() and (directory / "chunks.json").exists():
        array = np.load(directory / "embeddings.npy", allow_pickle=False)
        old_chunks = read_json(directory / "chunks.json")
        if len(old_chunks) == array.shape[0]:
            vectors.update((text_sha(c), row) for c, row in zip(old_chunks, array))
    return vectors


def load_embeddings(directory: Path, manifest: dict, chunks: list[dict]) -> np.ndarray:
    """The embedding matrix in chunk order, assembled from the stores after checking each one."""
    if manifest.get("schema_version") != INDEX_SCHEMA:
        raise ValueError("Index layout is out of date; rerun build_indexes")
    row_of = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    embeddings = np.zeros(tuple(manifest["embedding_shape"]), dtype=np.float32)
    filled = np.zeros(len(chunks), dtype=bool)
    for key, store in manifest["stores"].items():
        array_path, meta_path = directory / store["file"], directory / store["meta"]
        if file_sha(array_path) != store["sha256"]:
            raise ValueError(f"Saved embeddings for {key} do not match the index manifest")
        array = np.load(array_path, allow_pickle=False)
        meta = read_json(meta_path)
        if fingerprint({k: meta[k] for k in ("course", "level", "model", "chunk_ids", "text_sha256")}) != store["content_fingerprint"] \
                or array.shape[0] != len(meta["chunk_ids"]) != store["rows"]:
            raise ValueError(f"Embedding store {key} does not match the index manifest")
        for chunk_id, vector in zip(meta["chunk_ids"], array):
            if chunk_id not in row_of or filled[row_of[chunk_id]]:
                raise ValueError(f"Embedding store {key} lists an unknown or repeated page")
            embeddings[row_of[chunk_id]] = vector
            filled[row_of[chunk_id]] = True
    if not filled.all() or not np.isfinite(embeddings).all():
        raise ValueError("Invalid saved embeddings")
    return embeddings


def build(output_dir: Path, model_name: str = DEFAULT_MODEL, *, lexical_only: bool = False, offline: bool = False) -> dict:
    started = perf_counter()
    all_chunks = read_json(output_dir / "parsed_course_chunks.json")
    catalog = read_json(output_dir / "course_catalog_manifest.json")
    before = fingerprint({'chunks': all_chunks, 'catalog': catalog})
    mark_slide_clo_pages(all_chunks, catalog)
    if fingerprint({'chunks': all_chunks, 'catalog': catalog}) != before:
        write_json(output_dir / 'parsed_course_chunks.json', all_chunks)
        write_json(output_dir / 'course_catalog_manifest.json', catalog)
    chunks = [c for c in all_chunks if c.get("indexable", True) and search_text(c).strip()]
    if len({c["chunk_id"] for c in chunks}) != len(chunks):
        raise ValueError("Duplicate chunk IDs in input")
    if any(c["course_code"] not in COURSES or c["evidence_level"] not in LEVELS.values() for c in chunks):
        raise ValueError("Unexpected course or evidence level")
    directory = output_dir / "indexes"
    directory.mkdir(parents=True, exist_ok=True)
    model_label = None if lexical_only else model_name

    # Which stores changed: a store is its course and level's pages, identified by their text.
    groups = {(course, level): [i for i, c in enumerate(chunks) if c["course_code"] == course and evidence_levels(c)[0] == level]
              for course in COURSES for level in LEVELS.values()}
    metas, changed = {}, []
    for (course, level), rows in groups.items():
        meta = {"course": course, "level": level, "model": model_label,
                "chunk_ids": [chunks[i]["chunk_id"] for i in rows], "text_sha256": [text_sha(chunks[i]) for i in rows]}
        meta["content_fingerprint"] = fingerprint(meta)
        metas[(course, level)] = meta
        array_path, meta_path = store_files(directory, course, level)
        current = read_json(meta_path) if meta_path.exists() else {}
        if current.get("content_fingerprint") != meta["content_fingerprint"] or not array_path.exists():
            changed.append((course, level))

    # Vectors only for page text not seen before, encoded together as in a full build.
    reused = previous_vectors(directory, model_label)
    needed = sorted({i for key in changed for i in groups[key] if text_sha(chunks[i]) not in reused}) if model_label else []
    if needed:
        model = load_model(model_name, output_dir / "models", offline)
        encoded = np.asarray(model.encode([search_text(chunks[i]) for i in needed], normalize_embeddings=True,
                                          show_progress_bar=False), dtype=np.float32)
        reused.update(zip((text_sha(chunks[i]) for i in needed), encoded))
    dim = 0 if model_label is None else len(next(iter(reused.values()))) if reused else 0

    for course, level in changed:
        rows, meta = groups[(course, level)], metas[(course, level)]
        array_path, meta_path = store_files(directory, course, level)
        array_path.parent.mkdir(parents=True, exist_ok=True)
        vectors = np.asarray([reused[text_sha(chunks[i])] for i in rows], dtype=np.float32).reshape(len(rows), dim) \
            if model_label else np.empty((len(rows), 0), dtype=np.float32)
        np.save(array_path, vectors, allow_pickle=False)
        write_json(meta_path, meta)
    # Files of the earlier single-file layout are replaced by the stores.
    for legacy in ("embeddings.npy", "routed", "pooled"):
        path = directory / legacy
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    stores = {}
    for (course, level), meta in metas.items():
        array_path, meta_path = store_files(directory, course, level)
        stores[f"{course}::{level}"] = {"file": array_path.relative_to(directory).as_posix(),
                                        "meta": meta_path.relative_to(directory).as_posix(), "rows": len(meta["chunk_ids"]),
                                        "sha256": file_sha(array_path), "content_fingerprint": meta["content_fingerprint"]}
    write_json(directory / "chunks.json", chunks)
    write_json(directory / "catalog.json", catalog)
    partitions = {"routed": {}, "pooled": {}}
    for course in COURSES:
        pooled = [i for i, c in enumerate(chunks) if c["course_code"] == course]
        partitions["pooled"][course] = pooled
        for level in LEVELS.values():
            partitions["routed"][f"{course}::{level}"] = [
                i for i in pooled if level in evidence_levels(chunks[i]) and catalog["courses"][course]["level_availability"][level]]
    manifest = {
        "schema_version": INDEX_SCHEMA, "routing_policy": ROUTING_POLICY,
        "mode": "lexical_only_diagnostic" if lexical_only else "dense_bm25_hybrid",
        "model": model_label, "chunk_count": len(chunks),
        "source_fingerprint": fingerprint({"chunks": all_chunks, "catalog": catalog}),
        "index_fingerprint": fingerprint({"chunks": chunks, "catalog": catalog}),
        "embedding_shape": [len(chunks), dim], "stores": stores, "partitions": partitions,
        "fusion": FUSION, "rrf_k0": RRF_K0, "lexical_algorithm": "BM25Plus", "lexical_tokenizer": LEXICAL_TOKENIZER,
        "last_build": {"stores_rebuilt": [f"{c}::{l}" for c, l in changed], "stores_total": len(metas),
                       "vectors_computed": len(needed), "seconds": round(perf_counter() - started, 2)},
    }
    write_json(directory / "manifest.json", manifest)
    print(f"Built {manifest['mode']} indexes over {len(chunks)} identical chunks: "
          f"{len(changed)} of {len(metas)} stores rebuilt, {len(needed)} page vectors computed")
    return manifest


class Retriever:
    def __init__(self, output_dir: Path, *, offline: bool = False):
        directory = output_dir / "indexes"
        self.manifest = read_json(directory / "manifest.json")
        if self.manifest.get("schema_version") != INDEX_SCHEMA:
            raise ValueError("Index layout is out of date; rerun build_indexes")
        if self.manifest.get("routing_policy") != ROUTING_POLICY:
            raise ValueError("Index routing policy is stale; rerun build_indexes")
        if self.manifest.get("fusion") != FUSION:
            raise ValueError("Index fusion settings are stale; rerun build_indexes")
        if self.manifest.get("lexical_tokenizer") != LEXICAL_TOKENIZER:
            raise ValueError("Index lexical tokenizer is stale; rerun build_indexes")
        self.chunks = read_json(directory / "chunks.json")
        self.catalog = read_json(directory / "catalog.json")
        current = {"chunks": read_json(output_dir / "parsed_course_chunks.json"),
                   "catalog": read_json(output_dir / "course_catalog_manifest.json")}
        if fingerprint(current) != self.manifest["source_fingerprint"]:
            raise ValueError("Index is stale; rerun build_indexes")
        if fingerprint({"chunks": self.chunks, "catalog": self.catalog}) != self.manifest["index_fingerprint"]:
            raise ValueError("Index snapshots do not match the manifest")
        self.embeddings = load_embeddings(directory, self.manifest, self.chunks)
        self.model = None if self.manifest["model"] is None else load_model(
            self.manifest["model"], output_dir / "models", offline)
        self.bm25 = {}
        for kind, partitions in self.manifest["partitions"].items():
            for key, rows in partitions.items():
                corpus = [lexical_terms(search_text(self.chunks[i])) or ["emptydocument"] for i in rows]
                self.bm25[(kind, key)] = BM25Plus(corpus) if corpus else None
        self.query_vectors = {}

    def retrieve(self, course: str, query: str, level: str | None = None, top_k: int = 3) -> list[dict]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        kind, key = ("pooled", course) if level is None else ("routed", f"{course}::{level}")
        rows = self.manifest["partitions"][kind][key]
        if level and any(level not in evidence_levels(self.chunks[i]) for i in rows):
            raise ValueError("Wrong-level source in index partition; rebuild indexes")
        if not rows:
            return []
        terms = lexical_terms(query)
        lexical = np.maximum(0, np.asarray(self.bm25[(kind, key)].get_scores(terms)))
        # BM25Plus adds a query-dependent constant to every row. Remove the
        # nonmatching floor so rows without a query term are not ranked by BM25.
        term_sets = [set(lexical_terms(search_text(self.chunks[i]))) for i in rows]
        matching = np.array([bool(set(terms) & terms_in_doc) for terms_in_doc in term_sets])
        lexical[~matching] = 0
        lexical = lexical / lexical.max() if lexical.max() > 0 else lexical
        dense = np.zeros(len(rows))
        if self.model is not None:
            if query not in self.query_vectors:
                self.query_vectors[query] = np.asarray(self.model.encode([query], normalize_embeddings=True))[0]
            dense = np.clip(self.embeddings[rows] @ self.query_vectors[query], 0, 1)
        lexical_ranks = ranking(lexical)
        dense_ranks = ranking(dense) if self.model is not None else {}
        scores = reciprocal_rank_fusion([lexical_ranks, dense_ranks], len(rows), self.manifest["rrf_k0"])
        def rank_key(j):
            chunk = self.chunks[rows[j]]
            # Within the CI, pages with an explicit outcome or synopsis statement rank first.
            priority = (0 if has_official_commitment(chunk) else 1) if level == 'CLO' else 0
            return (priority, -scores[j], chunk['chunk_id'])
        ranked = sorted(range(len(rows)), key=rank_key)
        results = []
        for j in ranked:
            if scores[j] <= 0:
                continue
            chunk = self.chunks[rows[j]]
            results.append({
                "chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"], "course_code": course,
                "evidence_level": level or chunk["evidence_level"], "pdf_page_no": chunk["pdf_page_no"],
                "source_evidence_level": chunk["evidence_level"],
                "score": round(float(scores[j]), 6), "dense_score": round(float(dense[j]), 6),
                "lexical_score": round(float(lexical[j]), 6),
                "lexical_rank": lexical_ranks.get(j), "dense_rank": dense_ranks.get(j),
                "snippet": chunk["verbatim_text_span"][:320],
                "verbatim_text_span": chunk["verbatim_text_span"],
                "slide_or_section_title": (chunk.get("slide_or_section_title", "") + " — " +
                    ("Course Learning Outcomes" if explicit_clo_statement(chunk["verbatim_text_span"]) else "Course Synopsis"))
                    if has_official_commitment(chunk) else chunk.get("slide_or_section_title", ""),
                "extraction_methods_used": chunk["extraction_methods_used"],
                "visual_diagram_summary": chunk.get("visual_diagram_summary", ""),
            })
            if len(results) == top_k:
                break
        return results


def main() -> None:
    parser = base_parser(__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--lexical-only", action="store_true", help="Diagnostic BM25-only mode, explicitly labeled in reports")
    parser.add_argument("--offline", action="store_true", help="Only use an already cached embedding model")
    args = parser.parse_args()
    build(args.output_dir, args.model, lexical_only=args.lexical_only, offline=args.offline)


if __name__ == "__main__":
    main()
