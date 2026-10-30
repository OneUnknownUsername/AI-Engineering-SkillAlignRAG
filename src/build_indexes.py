"""Persist shared dense embeddings and routed/pooled BM25 corpus partitions."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Plus

from src.curriculum_scope import clo_evidence_window, has_official_commitment, refresh_auxiliary_clo_pages, explicit_clo_statement
from src.common import COURSES, LEVELS, base_parser, evidence_levels, fingerprint, read_json, tokens, write_json

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
STOPWORDS = set("a an the and or to of in on for with by is are be as how this that from at it its".split())


def search_text(chunk: dict) -> str:
    text = chunk["verbatim_text_span"]
    if has_official_commitment(chunk):
        # Rank on the commitment, rather than staff metadata and duplicate OCR prefixes.
        text = clo_evidence_window(text)[:3000]
    return "\n".join(filter(None, [text, chunk.get("visual_diagram_summary", "")]))


def catalog_overlap(query: str, card: dict) -> float:
    query_terms = set(tokens(query)) - STOPWORDS
    card_terms = set(tokens(card.get("deck_title", "") + " " + " ".join(
        card.get("declared_learning_outcomes_or_agenda", [])))) - STOPWORDS
    return len(query_terms & card_terms) / len(query_terms) if query_terms else 0.0


def load_model(model: str, directory: Path, offline: bool):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model, cache_folder=str(directory), local_files_only=offline, device="cpu")


def build(output_dir: Path, model_name: str = DEFAULT_MODEL, *, lexical_only: bool = False, offline: bool = False) -> dict:
    all_chunks = read_json(output_dir / "parsed_course_chunks.json")
    catalog = read_json(output_dir / "course_catalog_manifest.json")
    before = fingerprint({'chunks': all_chunks, 'catalog': catalog})
    refresh_auxiliary_clo_pages(all_chunks, catalog)
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
    model = None if lexical_only else load_model(model_name, output_dir / "models", offline)
    embeddings = np.empty((len(chunks), 0), dtype=np.float32)
    if model is not None and chunks:
        embeddings = np.asarray(model.encode([search_text(c) for c in chunks], normalize_embeddings=True,
                                             show_progress_bar=True), dtype=np.float32)
    np.save(directory / "embeddings.npy", embeddings, allow_pickle=False)
    write_json(directory / "chunks.json", chunks)
    write_json(directory / "catalog.json", catalog)
    partitions = {"routed": {}, "pooled": {}}
    for course in COURSES:
        pooled = [i for i, c in enumerate(chunks) if c["course_code"] == course]
        partitions["pooled"][course] = pooled
        write_json(directory / "pooled" / f"{course}.json", pooled)
        for level in LEVELS.values():
            rows = [i for i in pooled if level in evidence_levels(chunks[i]) and catalog["courses"][course]["level_availability"][level]]
            partitions["routed"][f"{course}::{level}"] = rows
            write_json(directory / "routed" / course / f"{level}.json", rows)
    manifest = {
        "schema_version": 2, "routing_policy": "strict_levels_official_clo_first_v2", "mode": "lexical_only_diagnostic" if lexical_only else "dense_bm25_hybrid",
        "model": None if lexical_only else model_name, "chunk_count": len(chunks),
        "source_fingerprint": fingerprint({"chunks": all_chunks, "catalog": catalog}),
        "index_fingerprint": fingerprint({"chunks": chunks, "catalog": catalog}),
        "embedding_shape": list(embeddings.shape), "partitions": partitions,
        "embedding_sha256": hashlib.sha256((directory / "embeddings.npy").read_bytes()).hexdigest(),
        "dense_weight": 0 if lexical_only else .5, "catalog_boost_weight": .15,
        "lexical_algorithm": "BM25Plus", "embedding_file": "embeddings.npy",
    }
    write_json(directory / "manifest.json", manifest)
    print(f"Built {manifest['mode']} indexes over {len(chunks)} identical chunks")
    return manifest


class Retriever:
    def __init__(self, output_dir: Path, *, offline: bool = False):
        directory = output_dir / "indexes"
        self.manifest = read_json(directory / "manifest.json")
        if self.manifest.get("routing_policy") != "strict_levels_official_clo_first_v2":
            raise ValueError("Index routing policy is stale; rerun build_indexes")
        self.chunks = read_json(directory / "chunks.json")
        self.catalog = read_json(directory / "catalog.json")
        current = {"chunks": read_json(output_dir / "parsed_course_chunks.json"),
                   "catalog": read_json(output_dir / "course_catalog_manifest.json")}
        if fingerprint(current) != self.manifest["source_fingerprint"]:
            raise ValueError("Index is stale; rerun build_indexes")
        if fingerprint({"chunks": self.chunks, "catalog": self.catalog}) != self.manifest["index_fingerprint"]:
            raise ValueError("Index snapshots do not match the manifest")
        self.embeddings = np.load(directory / "embeddings.npy", allow_pickle=False)
        if hashlib.sha256((directory / "embeddings.npy").read_bytes()).hexdigest() != self.manifest["embedding_sha256"]:
            raise ValueError("Saved embeddings do not match the index manifest")
        if list(self.embeddings.shape) != self.manifest["embedding_shape"] or not np.isfinite(self.embeddings).all():
            raise ValueError("Invalid saved embeddings")
        self.model = None if self.manifest["model"] is None else load_model(
            self.manifest["model"], output_dir / "models", offline)
        self.bm25 = {}
        for kind, partitions in self.manifest["partitions"].items():
            for key, rows in partitions.items():
                corpus = [tokens(search_text(self.chunks[i])) or ["emptydocument"] for i in rows]
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
        terms = tokens(query)
        lexical = np.maximum(0, np.asarray(self.bm25[(kind, key)].get_scores(terms)))
        # BM25Plus adds a query-dependent constant to every row. Remove the
        # nonmatching floor so catalog overlap alone cannot create lexical evidence.
        term_sets = [set(tokens(search_text(self.chunks[i]))) for i in rows]
        matching = np.array([bool(set(terms) & terms_in_doc) for terms_in_doc in term_sets])
        lexical[~matching] = 0
        lexical = lexical / lexical.max() if lexical.max() > 0 else lexical
        dense = np.zeros(len(rows))
        if self.model is not None:
            if query not in self.query_vectors:
                self.query_vectors[query] = np.asarray(self.model.encode([query], normalize_embeddings=True))[0]
            dense = np.clip(self.embeddings[rows] @ self.query_vectors[query], 0, 1)
        weight = self.manifest["dense_weight"]
        base = weight * dense + (1 - weight) * lexical
        boosts = np.zeros(len(rows))
        if level is not None:
            cards = {c["doc_id"]: c for c in self.catalog["courses"][course]["deck_aspect_cards"]}
            boosts = np.array([catalog_overlap(query, cards.get(self.chunks[i]["doc_id"], {}))
                               if self.chunks[i]["evidence_level"] == "Taught" else 0 for i in rows])
        scores = base + self.manifest["catalog_boost_weight"] * boosts * (base > 0)
        def rank_key(j):
            chunk = self.chunks[rows[j]]
            # Explicit CI commitments are primary; embedded lecture CLOs are secondary.
            priority = (0 if has_official_commitment(chunk) else 1 if chunk['evidence_level'] == 'Taught' else 2) if level == 'CLO' else 0
            return (priority, -scores[j], chunk['chunk_id'])
        ranked = sorted(range(len(rows)), key=rank_key)
        results = []
        for j in ranked:
            if base[j] <= 0:
                continue
            chunk = self.chunks[rows[j]]
            results.append({
                "chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"], "course_code": course,
                "evidence_level": level or chunk["evidence_level"], "pdf_page_no": chunk["pdf_page_no"],
                "source_evidence_level": chunk["evidence_level"],
                "auxiliary_evidence_levels": chunk.get("auxiliary_evidence_levels", []),
                "is_auxiliary_evidence": level is not None and level != chunk["evidence_level"],
                "score": round(float(scores[j]), 6), "dense_score": round(float(dense[j]), 6),
                "lexical_score": round(float(lexical[j]), 6), "catalog_overlap": round(float(boosts[j]), 6),
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
