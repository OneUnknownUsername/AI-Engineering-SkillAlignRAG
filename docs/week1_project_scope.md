# Lab Activity: Part C \- Semester Project Scoping and GitHub Setup

This document preserves the initial Week 1 scope. The later V1 decisions in
[the requirements](week2_requirements.md) supersede its provisional dataset
ranges and industry-source choices: V1 uses three courses, 12 HRD Corp IndSF-derived
tasks, PDF/PPTX/DOCX uploads, authorised staff access, and an interactive dashboard.
Citations follow the reference list in
[the Week 2 requirements](week2_requirements.md#references), which matches the SAIA3113
project proposal report.

## Step C2 \- Complete the Project Scoping Template (10 minutes)

| Project Name | SkillAlign-RAG  |
| :---- | :---- |
| Domain | Higher Education / Curriculum Quality Assurance |
| Problem Statement | Course lecturers struggle to manually verify whether specific industry skills are intended (CLO), taught (Taught), and evaluated (Assessed) across scattered course files. AI engineering makes it possible to build a source-routed, document-grounded RAG system that retrieves multi-level course evidence and verifies skill coverage with exact page/slide citations. |
| Evidence of the Problem | Course learning outcomes (CLOs), weekly teaching materials, and assessments are distributed across separate, heterogeneous university files (PDFs and PPTXs) with different granularity. Enabler E2 of Malaysia’s National AI Action Plan 2026–2030 (AI Nation 2030) proposes leveraging AI tools to review the curriculum quality and skills coverage of accredited skilling programmes (Ministry of Digital, 2026, p. 62); this project applies the idea at university level. |
| Initial Related Work (at least 3\) | **1\. Manual curriculum alignment reviews:** Thorough and contextual, but slow and unscalable across granular documents. **2\. Conventional single-pass RAG workflows:** Automated, but suffers from context dilution across mixed document types and conflates missing files (insufficient evidence) with confirmed skill absence. **3\. Probabilistic LLM chatbots:** Flexible, but prone to unverified citations and hallucinated source support. |
| Engineering Gap / Limitation | Conventional single-pass RAG suffers from semantic mismatch and context dilution when searching across mixed course files (syllabi vs. slides vs. rubrics) and lacks deterministic citation verification. |
| Initial Project Objectives (2-3) | **O1:** To construct a standardized curriculum evidence schema and ground-truth dataset from 3 to 5 core SAIAH courses (PDFs/PPTXs) preserving page/slide provenance. **O2:** To develop a source-routed RAG pipeline (CLO, Taught, Assessed) paired with a deterministic span-matching and NLI citation verifier to classify skill coverage (supported vs. not found / insufficient evidence). **O3:** To evaluate the system against a single-pass RAG baseline in terms of per-level Precision/Recall/F1, citation faithfulness, unsupported-claim rate, runtime, and token usage. |
| Target Users | University course lecturers and programme coordinators, specifically teaching core courses in the UTM SAIAH programme. |
| Data Sources (at least 2\) | **Source 1:** SAIAH course documents (3–5 courses)  containing CI PDFs (CLO), lecture PPTXs (Taught), and assessment rubrics (Assessed). **Source 2:** Industry Skill Benchmark containing a bounded set of 12–15 Malaysian AI industry skill tasks derived from published competency frameworks and curated job descriptions. |
| Similar to EduAdvisor | Both operate in Higher Education, ingest scattered university documents, and use retrieval-grounded AI (RAG) with guardrails to provide cited, trustworthy answers. |
| Different from EduAdvisor | Targets academic staff rather than students; uses source-routed multi-level retrieval (CLO, Taught, Assessed) and a non-prompt NLI citation verifier presented in a tabular review dashboard rather than a student Q\&A chatbot. |
| Responsible AI Risks (at least 2\) | **Risk 1 — Hallucination & unverified citations:** Model fabricates source spans or misinterprets vague text as skill support → mitigated via deterministic text-span matching \+ NLI entailment verification. **Risk 2 — Epistemic uncertainty:** Model conflates missing documentation (insufficient evidence) with confirmed skill absence → unfair evaluation of a course. **Risk 3 — Data privacy / confidentiality:** Confidential UTM course documents exposed to external APIs → mitigated by prioritizing local open-weight LLM inference. |

