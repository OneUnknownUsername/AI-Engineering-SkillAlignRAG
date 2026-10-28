"""Extract all IndSF role/skill records (B1), then retrieve graduate benchmark evidence (B2)."""
from __future__ import annotations

import re
import math
from collections import Counter
from pathlib import Path

import numpy as np

from src.build_indexes import DEFAULT_MODEL, STOPWORDS, load_model
from src.common import ROOT, base_parser, extraction_options, fingerprint, md, read_json, tokens, write_json
from src.extraction import extractor_from_args, unique_lines
from src.indsf_extraction import SECTIONS, extract_all_skills

BENCHMARK_FILES = {
    "artificial_intelligence": ["IndSF_Artificial_Intelligence.pdf", "HRD-Corp_IndSF_Artificial_Intelligence.pdf"],
    "data_science": ["IndSF_Data_Science_2023.pdf", "HRDCorp_IndSF_DataScience_2ndEdition.pdf"],
}
BUCKETS = {"A": range(1, 4), "B": range(4, 8), "C": range(8, 11), "D": range(11, 13)}
MATCH_WEIGHTS = {"semantic": .60, "keyword": .35, "sfia": .05}
SECTION_WEIGHTS = {'job_description_tasks': 1.15, 'competencies': 1.0, 'essential_skills': 0.90, 'common_tools': 0.70}


def validate_skills(skills: list[dict]) -> None:
    if not isinstance(skills, list) or any(not isinstance(s, dict) for s in skills) or {s.get("skill_id") for s in skills} != {f"S{i:02d}" for i in range(1, 13)} or len(skills) != 12:
        raise ValueError("Locked benchmark must contain exactly S01-S12 once each")
    for skill in skills:
        for field in ("skill_name", "bucket", "retrieval_query", "nli_hypothesis_template"):
            if not isinstance(skill.get(field), str) or not skill[field].strip():
                raise ValueError(f"{skill['skill_id']}: missing {field}")
        bucket = skill["bucket"].removeprefix("Bucket ").split(":")[0].strip()
        if bucket not in BUCKETS or int(skill["skill_id"][1:]) not in BUCKETS[bucket]:
            raise ValueError(f"{skill['skill_id']}: incorrect bucket")
        if not isinstance(skill.get("sfia_codes"), list) or not skill["sfia_codes"] or any(
            not isinstance(code, str) or not re.fullmatch(r"[A-Z]{4,6}", code) for code in skill["sfia_codes"]
        ):
            raise ValueError(f"{skill['skill_id']}: sfia_codes must be a nonempty list of uppercase locked code labels")


MANAGEMENT = re.compile(
    r"\b(?:recruits?|profitability|product marketing|product launches|steering committees|"
    r"board|commercial success|business strategy|product roadmap|resource allocation)\b|"
    r"(?:leads?|manages?) (?:a global|the organisation|.*\bteams?\b)|"
    r"(?:sets? (?:organisational )?(?:strategy|standards)|oversees|organisational policies)", re.I)
TECHNICAL = re.compile(
    r"\b(?:data|machine|learning|model\w*|AI|ML|algorithm\w*|program\w*|software|"
    r"system\w*|cloud|pipelines?|requirements?|visual\w*|statisti\w*|probability|calculus|"
    r"linear algebra|numerical|privacy|governance|ethic\w*|risk\w*|fair\w*|bias|"
    r"transparency|explain\w*|security|compliance|regulatory|deployment|testing|quality|"
    r"hyperparam\w*|tuning|prediction|features?|preprocess\w*|regression|classification|"
    r"clustering|regulari[sz]\w*)\b|\bframe(?:s|d)? the problem\b", re.I)


def exclusion_reason(item: dict) -> str | None:
    if item["section_type"] == "sfia_level_definitions":
        return "framework_definition"
    if item["seniority_tier"] not in {"entry_associate", "mid_level"}:
        return "senior_management"
    if MANAGEMENT.search(item["verbatim_text"]):
        return "management_duty"
    if not item["sfia_codes"] and item["section_type"] != "common_tools" and not TECHNICAL.search(item["verbatim_text"]):
        return "nontechnical"
    return None


def filter_graduate_items(items: list[dict]) -> list[dict]:
    return [item for item in items if exclusion_reason(item) is None]


def keyword_terms(text: str) -> set[str]:
    # Light stemming and spelling normalization complement the dense encoder.
    text = text.lower().replace("visualization", "visualisation").replace("modeling", "modelling").replace("analyze", "analyse")
    return {re.sub(r"e$", "", re.sub(r"(?:ing|es|s)$", "", t)) for t in tokens(text) if t not in STOPWORDS}


def definition_fingerprint(skill: dict) -> str:
    return fingerprint({k: skill[k] for k in ("skill_id", "skill_name", "bucket", "sfia_codes",
                                            "retrieval_query", "nli_hypothesis_template", "expected_primary_courses") if k in skill})


def compile_benchmark(skills: list[dict], items: list[dict], *, encoder=None, model_name: str = DEFAULT_MODEL,
                      model_dir: Path = ROOT / "outputs/models", offline: bool = False,
                      top_k: int = 3, min_score: float = .30) -> list[dict]:
    """Retrieve evidence solely from B1 records; supplied provenance is never used."""
    validate_skills(skills)
    if top_k < 1 or not 0 <= min_score <= 1:
        raise ValueError("top_k must be positive and min_score must be between 0 and 1")
    if items and "item_id" not in items[0]:
        items = extract_all_skills(items)
    retained = sorted(filter_graduate_items(items), key=lambda i: i["item_id"])
    if not retained:
        raise ValueError("Stage B1 contains no graduate-relevant technical records")
    ordered = sorted(skills, key=lambda s: s["skill_id"])
    encoder = encoder if encoder is not None else load_model(model_name, model_dir, offline)
    texts = [s["skill_name"] + ". " + s["retrieval_query"] for s in ordered]
    # Compound cluster names describe several aspects. Match their phrases as
    # well as the full description so a short source bullet is not diluted by
    # unrelated parts of a long benchmark definition.
    query_groups = [[text, skill["skill_name"], *[part.strip() for part in re.split(r"[,;&]", skill["skill_name"]) if part.strip()]]
                    for skill, text in zip(ordered, texts)]
    queries = [query for group in query_groups for query in group]
    vectors = np.asarray(encoder.encode(queries + [i["verbatim_text"] for i in retained],
                                        normalize_embeddings=True, show_progress_bar=False), dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[0] != len(queries) + len(retained) or not np.isfinite(vectors).all():
        raise ValueError("Semantic encoder returned invalid vectors")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Semantic encoder returned a zero vector")
    vectors /= norms
    similarities = np.clip(vectors[:len(queries)] @ vectors[len(queries):].T, 0, 1)
    dense = []
    offset = 0
    for group in query_groups:
        dense.append(similarities[offset:offset + len(group)].max(axis=0))
        offset += len(group)
    termsets = [keyword_terms(i["verbatim_text"]) for i in retained]
    frequencies = Counter(t for terms in termsets for t in terms)
    idf = {t: math.log((len(retained) + 1) / (count + 1)) + 1 for t, count in frequencies.items()}
    item_norms = [math.sqrt(sum(idf[t] ** 2 for t in terms)) for terms in termsets]
    compiled = []
    for row, skill in enumerate(ordered):
        title_terms = keyword_terms(skill["skill_name"])
        keyword_queries = []
        for query in query_groups[row]:
            query_weights = {t: idf.get(t, math.log(len(retained) + 1) + 1) * (2 if t in title_terms else 1) for t in keyword_terms(query)}
            query_norm = math.sqrt(sum(w ** 2 for w in query_weights.values()))
            keyword_queries.append((query_weights, query_norm))
        ranked = []
        for column, item in enumerate(retained):
            overlap = min(1., max(sum(weights[t] * idf[t] for t in weights.keys() & termsets[column]) /
                                 max(1e-12, norm * item_norms[column]) for weights, norm in keyword_queries))
            sfia = len(set(skill["sfia_codes"]) & set(item["sfia_codes"])) / len(skill["sfia_codes"])
            score = .60 * float(dense[row][column]) + .35 * overlap + .05 * sfia
            # Tool inventories support a skill but say less about a role's
            # expected practice than tasks, skills or competency statements.
            score *= SECTION_WEIGHTS[item["section_type"]]
            if score >= min_score:
                ranked.append((score, item, {"semantic": round(float(dense[row][column]), 6),
                                            "keyword": round(overlap, 6), "sfia": round(sfia, 6)}))
        ranked.sort(key=lambda match: (-match[0], match[1]["item_id"]))
        provenance, seen_text = [], set()
        for score, item, components in ranked:
            # Identical text across different roles is still retained in B1, but
            # should not occupy every evidence slot for one benchmark cluster.
            key = item["verbatim_text"].casefold()
            if key in seen_text:
                continue
            seen_text.add(key)
            provenance.append({**{k: item[k] for k in ("item_id", "doc_id", "role_title", "pdf_page_no", "section_type")},
                               "matched_source_excerpt": item["verbatim_text"], "match_score": round(score, 6),
                               "score_components": components})
            if len(provenance) == top_k:
                break
        definition = {k: v for k, v in skill.items() if k not in {"indsf_provenance", "provided_indsf_provenance"}}
        compiled.append({**definition, "indsf_provenance": provenance,
                         "provenance_verified": bool(provenance), "mapping_status": "mapped" if provenance else "no_match",
                         "mapping_method": "dense_semantic_keyword_sfia", "semantic_model": model_name,
                         "mapping_parameters": {"top_k": top_k, "min_score": min_score,
                                                "weights": dict(MATCH_WEIGHTS),
                                                "section_weights": dict(SECTION_WEIGHTS),
                                                "semantic_queries": "max_title_phrases_and_description",
                                                "keywords": "max_phrase_idf_cosine_title_weight_2"},
                         "skill_definition_fingerprint": definition_fingerprint(skill),
                         "stage_b1_fingerprint": fingerprint(items), "sfia_mapping_status": "user_locked_labels"})
    return compiled


def verify_benchmark(skills: list[dict], raw: list[dict], items: list[dict] | None = None) -> None:
    """Check saved evidence against regenerated records without loading a model."""
    validate_skills(skills)
    expected = extract_all_skills(raw)
    if items is not None and items != expected:
        raise ValueError("Stage B1 records do not match the extracted pages")
    by_id = {i["item_id"]: i for i in expected}
    for skill in skills:
        if skill.get("skill_definition_fingerprint") != definition_fingerprint(skill):
            raise ValueError(f"{skill['skill_id']}: stale skill definition fingerprint")
        if skill.get("stage_b1_fingerprint") != fingerprint(expected):
            raise ValueError(f"{skill['skill_id']}: stale Stage B1 fingerprint")
        sources = skill.get("indsf_provenance", [])
        parameters = skill.get("mapping_parameters", {})
        if parameters.get("weights") != MATCH_WEIGHTS or parameters.get("section_weights") != SECTION_WEIGHTS or not isinstance(parameters.get("top_k"), int) or parameters["top_k"] < 1:
            raise ValueError(f"{skill['skill_id']}: invalid mapping parameters")
        if len(sources) > parameters["top_k"]:
            raise ValueError(f"{skill['skill_id']}: too many evidence items")
        if skill.get("mapping_status") != ("mapped" if sources else "no_match") or skill.get("provenance_verified") != bool(sources):
            raise ValueError(f"{skill['skill_id']}: inconsistent mapping status")
        if len({s.get('item_id') for s in sources}) != len(sources):
            raise ValueError(f"{skill['skill_id']}: duplicate evidence items")
        for source in sources:
            item = by_id.get(source.get("item_id"))
            if item is None or exclusion_reason(item):
                raise ValueError(f"{skill['skill_id']}: provenance is not an eligible Stage B1 record")
            if any(source.get(k) != item[k] for k in ("doc_id", "role_title", "pdf_page_no", "section_type")) or source.get("matched_source_excerpt") != item["verbatim_text"]:
                raise ValueError(f"{skill['skill_id']}: provenance differs from its Stage B1 record")
            if not isinstance(source.get("match_score"), (float, int)) or not 0 <= source["match_score"] <= 1:
                raise ValueError(f"{skill['skill_id']}: invalid match score")
            components = source.get("score_components", {})
            if set(components) != set(MATCH_WEIGHTS) or any(
                not isinstance(v, (float, int)) or not 0 <= v <= 1 for v in components.values()
            ):
                raise ValueError(f"{skill['skill_id']}: invalid score components")
            total = sum(MATCH_WEIGHTS[k] * v for k, v in components.items()) * SECTION_WEIGHTS[item["section_type"]]
            if abs(total - source["match_score"]) > 2e-6 or source["match_score"] + 1e-6 < parameters["min_score"]:
                raise ValueError(f"{skill['skill_id']}: inconsistent match score")


def write_quality_report(output_dir: Path, raw: list[dict], items: list[dict], compiled: list[dict] | None = None) -> None:
    counts = Counter((i["doc_id"], i["role_title"], i["section_type"]) for i in items)
    raw_counts = Counter()
    for item in items:
        raw_counts[item["doc_id"], item["role_title"], item["section_type"]] += len(item["source_occurrences"])
    roles = {(i["doc_id"], i["role_title"]) for i in items if i["scope"] == "role"}
    base_roles = {(i["doc_id"], i["base_role_title"]) for i in items if i["scope"] == "role"}
    reasons = Counter(exclusion_reason(i) or "retained" for i in items)
    occurrences = sum(len(i["source_occurrences"]) for i in items)
    report = ["# IndSF extraction and benchmark quality", "", "## Stage B1 - Full-document extraction", "",
              f"Pages parsed: {len(raw)}. Total roles detected: {len(roles)} (including table seniority variants); "
              f"career-role profiles: {len(base_roles)}.",
              f"Raw item occurrences: {occurrences}; unique extracted records: {len(items)}; "
              f"duplicate source occurrences merged: {occurrences - len(items)}.", "",
              "Each table cell shows unique records / raw occurrences before deduplication. "
              "Counts include tasks, skills, competencies, tools and framework definitions. "
              "A competency row produces one record per role/seniority column, with the original SFIA levels retained. "
              "Framework-wide appendices are not attributed to a career role. Text is whitespace/OCR-normalized; "
              "source_occurrences retains source locations and table rows for audit.", "",
              "| Document | Role | " + " | ".join(SECTIONS) + " | Total |",
              "| --- | --- | " + " | ".join("---" for _ in SECTIONS) + " | --- |"]
    for doc, role in sorted({(i["doc_id"], i["role_title"]) for i in items}):
        values = [counts[doc, role, section] for section in SECTIONS]
        raw_values = [raw_counts[doc, role, section] for section in SECTIONS]
        report.append(f"| {md(doc)} | {md(role)} | " + " | ".join(f"{v} / {r}" for v, r in zip(values, raw_values)) + f" | {sum(values)} / {sum(raw_values)} |")
    report += ["", "## Stage B2 - Graduate filtering", "",
               f"Retained graduate technical items: {reasons['retained']}. Excluded senior/management items: "
               f"{reasons['senior_management'] + reasons['management_duty']}. "
               f"Other exclusions: {reasons['framework_definition'] + reasons['nontechnical']}.", "",
               "| Decision | Items |", "| --- | --- |"]
    report.extend(f"| {reason} | {count} |" for reason, count in sorted(reasons.items()))
    report += ["", "## Automated S01-S12 mapping", ""]
    if compiled is None:
        report.append("Stage B2 has not completed. Stage B1 records are available; --extract-only intentionally stops here.")
    else:
        report += ["Hybrid score = 0.60 semantic cosine + 0.35 IDF keyword cosine (title terms weighted twice) + 0.05 SFIA overlap. "
                   "Both text scores take the best match across the full query, cluster name and its comma/ampersand-separated phrases. "
                   "Common-tool inventories receive a 0.8 evidence weight; tasks, skills and competencies receive 1.0. "
                   "Matches below the configured minimum score are omitted; empty clusters are reported as no_match. "
                   "Retrieval similarity supports source discovery and does not certify complete coverage of a cluster. "
                   "Locked code labels (including ETHICS and MELT) are preserved as supplied.", "",
                   f"Semantic model: {compiled[0]['semantic_model']}; parameters: {compiled[0]['mapping_parameters']}.", "",
                   "| Skill | Extracted item / document / page / role / section | Score | Source excerpt |", "| --- | --- | --- | --- |"]
        for skill in compiled:
            if not skill["indsf_provenance"]:
                report.append(f"| {skill['skill_id']} {md(skill['skill_name'])} | no_match | - | - |")
            for source in skill["indsf_provenance"]:
                label = f"{source['item_id']} / {source['doc_id']} p{source['pdf_page_no']} / {source['role_title']} / {source['section_type']}"
                report.append(f"| {skill['skill_id']} {md(skill['skill_name'])} | {md(label)} | {source['match_score']:.4f} | {md(source['matched_source_excerpt'])} |")
    report += ["", "## Page extraction telemetry", "", "| Document | PDF page | OCR | Vision | PII events |", "| --- | --- | --- | --- | --- |"]
    report.extend(f"| {md(p['doc_id'])} | {p['pdf_page_no']} | {p.get('ocr_status', 'unknown')} | "
                  f"{md(p.get('vision_error') or ('extracted' if p.get('visual_diagram_summary') else 'not_used'))} | "
                  f"{len(p.get('redaction_events', []))} |" for p in raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "indsf_quality_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def extract_indsf(data_dir: Path, output_dir: Path, extractor) -> list[dict]:
    directory = data_dir / "industry_benchmark"
    raw, issues = [], []
    for framework, aliases in BENCHMARK_FILES.items():
        matches = [directory / name for name in aliases if (directory / name).is_file()]
        if len(matches) != 1:
            issues.append({"framework": framework, "error": "Expected exactly one recognized PDF", "candidates": aliases})
            continue
        path = matches[0]
        print(f"Extracting benchmark {path.name}", flush=True)
        for page in extractor.extract(path):
            # Keep the original deterministic union for citation checking. This companion
            # field removes repeated bullet lines without changing source provenance.
            cleaned = unique_lines("\n".join([page["native_text"], page["ocr_extracted_text"]]))
            raw.append({"doc_id": path.name, "framework": framework, **page,
                        "deduplicated_text": cleaned})
    write_json(output_dir / "indsf_raw_extracted.json", raw)
    write_json(output_dir / "indsf_extraction_issues.json", issues)
    if issues:
        raise ValueError("Missing or ambiguous IndSF PDFs; inspect indsf_extraction_issues.json")
    return raw


def main() -> None:
    parser = base_parser(__doc__)
    extraction_options(parser)
    parser.add_argument("--skills-config", type=Path, default=ROOT / "config/benchmark_skills.json")
    parser.add_argument("--extract-only", action="store_true", help="Run B1 and its quality report without semantic compilation")
    parser.add_argument("--reuse-extraction", action="store_true", help="Compile existing extracted pages without rerunning OCR")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Local sentence-transformers semantic encoder")
    parser.add_argument("--offline", action="store_true", help="Use only a cached semantic model")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-match-score", type=float, default=.30)
    args = parser.parse_args()
    # Remove an earlier compiled artifact before validation, so a failed compile cannot leave stale skills.
    target = args.output_dir / "industry_skills_benchmark.json"
    target.unlink(missing_ok=True)
    (args.output_dir / "benchmark_provenance_resolution_report.md").unlink(missing_ok=True)
    raw = read_json(args.output_dir / "indsf_raw_extracted.json") if args.reuse_extraction else extract_indsf(
        args.data_dir, args.output_dir, extractor_from_args(args))
    items = extract_all_skills(raw)
    write_json(args.output_dir / "indsf_all_extracted_skills.json", items)
    write_quality_report(args.output_dir, raw, items)
    if not items:
        raise ValueError("Stage B1 extracted no structured records; inspect indsf_raw_extracted.json and indsf_quality_report.md")
    if not args.extract_only:
        if not args.skills_config.is_file():
            parser.error(f"Locked S01-S12 mapping required: {args.skills_config}; see config/README.md")
        compiled = compile_benchmark(read_json(args.skills_config), items, model_name=args.model,
                                     model_dir=args.output_dir / "models", offline=args.offline,
                                     top_k=args.top_k, min_score=args.min_match_score)
        verify_benchmark(compiled, raw, items)
        write_json(target, compiled)
        write_quality_report(args.output_dir, raw, items, compiled)
        unmatched = [s["skill_id"] for s in compiled if s["mapping_status"] == "no_match"]
        print(f"B1: {len(items)} records; B2: {len(filter_graduate_items(items))} eligible; "
              f"{len(compiled) - len(unmatched)}/12 clusters mapped. Unmatched: {unmatched}")
    else:
        print(f"B1: extracted {len(items)} unique records")


if __name__ == "__main__":
    main()
