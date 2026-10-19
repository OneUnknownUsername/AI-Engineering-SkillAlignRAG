# SkillAlign-RAG

> A document-grounded AI engineering system that helps UTM lecturers and programme coordinators verify whether industry skills are intended, taught, and assessed across course materials, with exact page and slide citations.

## Problem Statement

Course lecturers struggle to manually verify whether specific industry skills are covered across scattered course information PDFs, lecture slides, and assessment rubrics. In the UTM SAIAH programme, learning outcomes, weekly teaching materials, and assessments are distributed across heterogeneous files with different levels of detail.

SkillAlign-RAG addresses this gap with source-routed retrieval for three evidence levels:

- **CLO:** whether a skill is intended in the course learning outcomes.
- **Taught:** whether a skill is covered in weekly teaching materials.
- **Assessed:** whether a skill is evaluated in assessments or rubrics.

The system is designed to distinguish **Supported** evidence from **Not Found / Insufficient Evidence**. Missing documentation is not treated as proof that a skill is absent.

## Evidence of the Problem

- Course learning outcomes, teaching activities, and assessments are distributed across separate university files, making curriculum alignment difficult to review consistently. [Source: Eberly Center, course alignment guidance](https://www.cmu.edu/teaching/assessment/basics/alignment.html)
- Malaysia's National AI Action Plan 2026–2030 identifies curriculum quality and AI skills coverage as part of the national talent-development context. [Source: AI Nation 2030, Strategic Context and Foundational Enablers](https://ai.gov.my/aiactionplan2030/)

## Engineering Gap

Existing approaches are useful but incomplete for this task:

- **Manual curriculum alignment reviews** are contextual and thorough, but slow and difficult to scale across granular documents.
- **Conventional single-pass RAG** can suffer from semantic mismatch and context dilution when searching mixed course files, and may conflate missing files with confirmed skill absence.
- **Probabilistic LLM chatbots** can provide flexible answers, but may generate unsupported claims or unverified citations.

SkillAlign-RAG focuses on source-routed multi-level retrieval and deterministic citation verification to address these limitations.

## Project Objectives

- **O1:** Construct a standardized curriculum evidence schema and ground-truth dataset from 3–5 core SAIAH courses using PDFs and PPTXs while preserving page and slide provenance.
- **O2:** Develop a source-routed RAG pipeline for CLO, Taught, and Assessed evidence, paired with deterministic span matching and NLI-based citation verification, to classify skill coverage as **Supported** or **Not Found / Insufficient Evidence**.
- **O3:** Evaluate the system against a single-pass RAG baseline using per-level Precision, Recall, and F1; citation faithfulness; unsupported-claim rate; runtime; and token usage.

## Target Users

University course lecturers and programme coordinators teaching or overseeing core courses in the UTM SAIAH programme.

## Data Sources

- **SAIAH course documents:** Materials from 3–5 core courses, including course information PDFs for CLO evidence, lecture PPTXs for Taught evidence, and assessment rubrics for Assessed evidence.
- **Industry Skill Benchmark:** A bounded set of 12–15 Malaysian AI industry skill tasks derived from published competency frameworks and curated job descriptions.

Specific document URLs and the final benchmark sources will be recorded when the course materials and benchmark are selected.

## System Direction

The planned workflow is:

1. Ingest and normalize PDFs and PPTXs into a common evidence schema.
2. Preserve page, slide, course, document-type, and evidence-level provenance.
3. Route each skill query to the relevant CLO, Taught, or Assessed evidence collection.
4. Retrieve candidate passages and verify citations with exact span matching and NLI entailment checks.
5. Present per-skill coverage judgements, supporting evidence, and uncertainty in a tabular review dashboard.

## Responsible AI Risks

- **Hallucination and unverified citations:** Mitigated through deterministic text-span matching and NLI entailment verification.
- **Epistemic uncertainty:** Missing documentation must remain insufficient evidence rather than being interpreted as confirmed skill absence.
- **Data privacy and confidentiality:** Confidential course documents should not be exposed unnecessarily to external APIs; local open-weight model inference is preferred where practical.

## Similarity and Differentiation

Like EduAdvisor, SkillAlign-RAG operates in higher education, ingests scattered university documents, and uses retrieval-grounded AI with guardrails. It differs by targeting academic staff rather than students, using source-routed multi-level retrieval and a non-prompt NLI citation verifier, and presenting results in a curriculum review dashboard rather than a student Q&A chatbot.

## Weekly Progress

| Week | Focus | Deliverable | Status |
|------|-------|-------------|--------|
| W1 | System map and project scope | README and project-scoping documentation | Complete |
