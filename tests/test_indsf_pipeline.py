from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from src.common import read_json, write_json
from src.indsf_extraction import extract_all_skills
from src.pipeline_b_indsf_skills import compile_benchmark, exclusion_reason, main, verify_benchmark, write_quality_report


def page(number, text, tables="", doc="IndSF_Data_Science_2023.pdf"):
    return {"doc_id": doc, "pdf_page_no": number, "native_text": text,
            "verbatim_text_span": " ".join(text.split()), "tables_markdown": tables}


def definitions():
    # Canonical definitions are inputs; no curated citations are needed.
    from src.common import ROOT
    return [{k: v for k, v in s.items() if k != "indsf_provenance"}
            for s in read_json(ROOT / "config/benchmark_skills.json")]


class SemanticEncoder:
    def encode(self, texts, **kwargs):
        return np.array([[1., 0., 0.] if any(w in t.lower() for w in ["clean", "impute"])
                         else [0., 0., 1.] if t.startswith("Design database") else [0., 1., 0.] for t in texts])


def test_role_detection_continuation_ocr_codes_noise_and_repeated_pages():
    raw = [page(1, "ASSOCIATE AI/ML ENGINEER\nCAREER PATHWAYS\nSenior AI/ML Engineer\nJOB DESCRIPTION\n"
                   "Assists with data pipelines.\nDesigns data stores."),
           page(2, "ASSOCIATE AI/ML ENGINEER\nJOB DESCRIPTION (CON'T)\nAssists with data pipelines."),
           page(3, "ASSOCIATE AI/ML ENGINEER\nESSENTIAL SKILLS\nRequirement definition\n(REQM)\n"
                   "Data engineering (DENG)\nMachine learning (MLNG)\nCOMMON TOOLS\nWorkbench\u00a7"),
           page(4, "SENIOR AI/ML ENGINEER\nJOB DESCRIPTION\nDesigns data stores.")]
    raw[2]["ocr_extracted_text"] = "COMMON TOOLS\nData visualisation (VISL)"
    items = extract_all_skills(raw)
    repeated = next(i for i in items if i["verbatim_text"] == "Assists with data pipelines.")
    assert repeated["role_title"] == "Associate AI/ML Engineer"
    assert repeated["seniority_tier"] == "entry_associate"
    assert [s["pdf_page_no"] for s in repeated["source_occurrences"]] == [1, 2]
    assert any(i["verbatim_text"] == "Workbench" for i in items)
    assert {c for i in items for c in i["sfia_codes"]} == {"REQM", "DENG", "MLNG", "VISL"}
    assert any(i["seniority_tier"] == "senior_management" for i in items)
    assert len({i["item_id"] for i in items}) == len(items)
    assert extract_all_skills(list(reversed(raw))) == items


def test_tables_preserve_seniority_columns_and_appendices_without_role_leakage():
    table = ("| Skills | Data Analyst | Senior Data Analyst | Principle Data Analyst | Data Analyst Head |\n"
             "| --- | --- | --- | --- | --- |\n"
             "| Data Science (DATS) | 2,3 | 4,5 | 6 | 7 |")
    raw = [page(1, "JOB DESCRIPTION\nThis section describes the key functions of a data analyst:\n"
                   "Collect and clean data from various\nsources for analysis."),
           page(2, "SKILLS AND COMPETENCIES\nCOMMON TOOLS\n"
                   "This section lists the common tools used by a data\nanalyst:\n"
                   "Data preparation tools\nData visualisation tools\nNote:", table),
           page(3, "Appendix A", "| Level | Responsibility |\n| 2 | Assist |\n| 7 | Set Strategy, Inspire, and Mobilise |"),
           page(4, "Appendix B\nCOMMON TOOLS", "| COMMON TOOLS | EXAMPLES |\n| Programming Tools | Python, R |"),
           page(5, "Appendix C\nCOMMON CERTIFICATION\nData Science Certificate")]
    items = extract_all_skills(raw)
    competencies = [i for i in items if i["section_type"] == "competencies"]
    assert [i["sfia_levels"] for i in competencies] == [[2, 3], [4, 5], [6], [7]]
    assert [i["seniority_tier"] for i in competencies] == ["mid_level"] + ["senior_management"] * 3
    assert all(i["sfia_codes"] == ["DATS"] for i in competencies)
    assert len([i for i in items if i["section_type"] == "sfia_level_definitions"]) == 2
    assert any(i["scope"] == "framework" and "Python" in i["verbatim_text"] for i in items)
    assert not any("Certificate" in i["verbatim_text"] for i in items)
    assert len([i for i in items if i["section_type"] == "common_tools" and i["scope"] == "role"]) == 2
    task = next(i for i in items if i["section_type"] == "job_description_tasks")
    assert task["verbatim_text"] == "Collect and clean data from various sources for analysis."


def test_graduate_filter_excludes_senior_and_management_duties_but_keeps_ethics():
    raw = [page(1, "AI ETHICS OFFICER\nJOB DESCRIPTION\nIdentifies fairness and bias risks in AI models.\n"
                   "Recruits a global data team.\nCOMMON TOOLS\nFairlearn"),
           page(2, "AI PRODUCT MANAGER\nJOB DESCRIPTION\nWrites requirements for AI models."),
           page(3, "SENIOR AI/ML ENGINEER\nJOB DESCRIPTION\nEvaluates model performance.")]
    items = extract_all_skills(raw)
    assert exclusion_reason(next(i for i in items if "fairness" in i["verbatim_text"])) is None
    assert exclusion_reason(next(i for i in items if "Recruits" in i["verbatim_text"])) == "management_duty"
    assert all(exclusion_reason(i) == "senior_management" for i in items if i["role_title"] != "AI Ethics Officer")


def test_short_technical_essential_skills_survive_filtering():
    items = extract_all_skills([page(1, "AI Application Developer\nESSENTIAL SKILLS\n"
                                      "a) Frame the problem\nb) Hyperparameter\nc) Tuning Prediction")])
    assert len(items) == 3
    assert all(exclusion_reason(i) is None for i in items)


def test_semantic_mapping_does_not_need_keyword_overlap_or_input_provenance():
    raw = [page(1, "Data Analyst\nJOB DESCRIPTION\nImpute absent observations."),
           page(2, "Senior Data Analyst\nJOB DESCRIPTION\nClean missing data and preprocess data."),
           page(3, "Data Engineer\nJOB DESCRIPTION\nDesign database systems.")]
    # The paraphrase is technical even without lexical overlap with S01.
    raw[0]["native_text"] = raw[0]["native_text"].replace("observations", "data observations")
    items = extract_all_skills(raw)
    skills = definitions()
    compiled = compile_benchmark(skills, items, encoder=SemanticEncoder(), top_k=1, min_score=.5)
    source = compiled[0]["indsf_provenance"][0]
    assert "Impute" in source["matched_source_excerpt"]
    assert source["role_title"] == "Data Analyst"
    assert source["score_components"]["semantic"] == 1
    assert source["score_components"]["sfia"] == 0
    assert compiled[1]["mapping_status"] == "no_match"
    verify_benchmark(compiled, raw, items)
    for field, replacement in [("item_id", "invented"), ("pdf_page_no", 99),
                               ("matched_source_excerpt", "invented"), ("match_score", float("nan")),
                               ("match_score", .51)]:
        damaged = deepcopy(compiled)
        damaged[0]["indsf_provenance"][0][field] = replacement
        with pytest.raises(ValueError):
            verify_benchmark(damaged, raw)
    changed = deepcopy(raw)
    changed[0]["native_text"] += "\nApply statistical models."
    with pytest.raises(ValueError, match="stale"):
        verify_benchmark(compiled, changed)
    compiled[0]["retrieval_query"] = "A changed cluster definition"
    with pytest.raises(ValueError, match="stale skill"):
        verify_benchmark(compiled, raw)


def test_quality_report_accounts_for_records_and_all_clusters(tmp_path):
    raw = [page(1, "Data Analyst\nJOB DESCRIPTION\nClean missing data.")]
    items = extract_all_skills(raw)
    compiled = compile_benchmark(definitions(), items, encoder=SemanticEncoder())
    write_quality_report(tmp_path, raw, items, compiled)
    report = (tmp_path / "indsf_quality_report.md").read_text()
    assert "career-role profiles: 1" in report and "unique extracted records: 1" in report
    assert "Retained graduate technical items: 1" in report
    assert all(f"S{i:02}" in report for i in range(1, 13))
    assert items[0]["item_id"] in report


def test_empty_input_and_invalid_semantic_results_are_explicit_errors():
    with pytest.raises(ValueError, match="no graduate"):
        compile_benchmark(definitions(), [], encoder=SemanticEncoder())
    raw = [page(1, "Data Analyst\nJOB DESCRIPTION\nClean data.")]
    class BrokenEncoder:
        def encode(self, texts, **kwargs):
            return np.full((len(texts), 2), np.nan)
    with pytest.raises(ValueError, match="invalid vectors"):
        compile_benchmark(definitions(), raw, encoder=BrokenEncoder())


def test_native_competency_fallback_and_normalized_page_spans():
    raw = [page(1, "Data Analyst\nSKILLS AND COMPETENCIES\nSkills\nData\nAnalyst\nSenior\nPrincipal\nHead\n"
                   "Data Science (DATS)\n2,3\n4,5\n6\n7\nCOMMON TOOLS\nPython"),
           {"doc_id": "other.pdf", "pdf_page_no": 1, "verbatim_text_span":
            "Associate AI/ML Engineer JOB DESCRIPTION Applies machine learning techniques. Evaluates model performance."}]
    items = extract_all_skills(raw)
    assert len([i for i in items if i["section_type"] == "competencies"]) == 4
    assert [i["verbatim_text"] for i in items if i["doc_id"] == "other.pdf"] == [
        "Applies machine learning techniques.", "Evaluates model performance."]


def test_ocr_only_pages_preserve_short_tool_names_and_wrapped_codes():
    raw = [{"doc_id": "scan.pdf", "pdf_page_no": 1, "native_text": "", "ocr_extracted_text":
            "AI/ML ENGINEER\nESSENTIAL SKILLS\nMachine learning\n(MLNG)\nCOMMON TOOLS\nPython\nR\nWorkbench\u00a7"}]
    items = extract_all_skills(raw)
    assert {i["verbatim_text"] for i in items} == {"Machine learning (MLNG)", "Python", "R", "Workbench"}
    assert all(i["source_occurrences"][0]["source_field"] == "ocr_extracted_text" for i in items)


def test_appendix_tools_without_markdown_tables():
    raw = [page(1, "Appendix B\nCOMMON TOOLS\nEXAMPLES\nProgramming Tools\nPython, R\n"
                   "Data Visualisation Tools\nTableau, Power BI\nDisclaimer:\nNot exhaustive.")]
    items = extract_all_skills(raw)
    assert [i["verbatim_text"] for i in items] == ["Programming Tools: Python, R", "Data Visualisation Tools: Tableau, Power BI"]
    assert all(i["scope"] == "framework" for i in items)


def test_extract_only_cli_writes_b1_and_invalidates_previous_compilation(tmp_path, monkeypatch):
    raw = [page(1, "Data Analyst\nJOB DESCRIPTION\nClean data.")]
    write_json(tmp_path / "indsf_raw_extracted.json", raw)
    write_json(tmp_path / "industry_skills_benchmark.json", ["stale"])
    monkeypatch.setattr("sys.argv", ["pipeline_b", "--reuse-extraction", "--extract-only", "--output-dir", str(tmp_path)])
    main()
    assert read_json(tmp_path / "indsf_all_extracted_skills.json") == extract_all_skills(raw)
    assert not (tmp_path / "industry_skills_benchmark.json").exists()
    assert "Stage B2 has not completed" in (tmp_path / "indsf_quality_report.md").read_text()
