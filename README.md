# SkillAlign-RAG: A Retrieval-Augmented Generation System for Verifying Industry Skill Alignment Across Course Learning Outcomes, Teaching Materials, and Assessments

> A document-grounded AI engineering system that helps UTM lecturers and programme coordinators verify whether industry skills are intended, taught, and assessed across course materials, with exact page and slide citations.

## Problem Statement

Course lecturers struggle to manually verify whether specific industry skills are covered across scattered course information PDFs, lecture slides, and assessment rubrics. In the UTM SAIAH programme, learning outcomes, weekly teaching materials, and assessments are distributed across heterogeneous files with different levels of detail. AI engineering is appropriate because source-routed retrieval, document provenance, and citation verification can produce evidence-backed skill-coverage judgements while distinguishing insufficient evidence from confirmed skill absence.

## Evidence of the Problem

- Course learning outcomes, teaching activities, and assessments are distributed across separate university files, making curriculum alignment difficult to review consistently. [Source: Eberly Center, course alignment guidance](https://www.cmu.edu/teaching/assessment/basics/alignment.html)
- Malaysia's National AI Action Plan 2026–2030 identifies curriculum quality and AI skills coverage as part of the national talent-development context. [Source: AI Nation 2030, Strategic Context and Foundational Enablers](https://ai.gov.my/aiactionplan2030/)

## Initial Related Work / Existing Approaches

- **Manual curriculum alignment reviews:** Lecturers compare learning outcomes, teaching activities, and assessments. This approach is contextual and thorough, but slow and difficult to scale across granular documents. [Source: Eberly Center, course alignment guidance](https://www.cmu.edu/teaching/assessment/basics/alignment.html)
- **Conventional single-pass RAG:** Retrieved passages can support knowledge-intensive answers, but mixed course files create context dilution and the workflow does not provide the source-routed, page/slide-level verification required here. [Source: Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- **Keyword search:** Exact-term search is fast, but semantic mismatch between academic terminology and industry skill phrasing can reduce recall. [Source: Manning, Raghavan, and Schutze, Introduction to Information Retrieval, Chapter 9](https://nlp.stanford.edu/IR-book/html/htmledition/relevance-feedback-and-query-expansion-1.html)

## Project Objectives

- O1: To construct a standardized curriculum evidence schema and ground-truth dataset from 3–5 core SAIAH courses using PDFs and PPTXs while preserving page and slide provenance.
- O2: To develop a source-routed RAG pipeline for CLO, Taught, and Assessed evidence, paired with deterministic span matching and NLI-based citation verification, to classify skill coverage as Supported or Not Found / Insufficient Evidence.
- O3: To evaluate the system against a single-pass RAG baseline using per-level Precision, Recall, and F1; citation faithfulness; unsupported-claim rate; runtime; and token usage.

## Target Users

University course lecturers and programme coordinators teaching or overseeing core courses in the UTM SAIAH programme.

## Data Sources

- SAIAH course documents: course information PDFs, lecture PPTXs, and assessment rubrics from 3–5 core courses — URL: pending provision by the course team.
- Industry Skill Benchmark: a bounded set of 12–15 Malaysian AI industry skill tasks derived from published competency frameworks and curated job descriptions — URL: pending benchmark curation and source selection.

## Weekly Progress

| Week | Focus | Deliverable | Status |
|------|-------|-------------|--------|
| W1 | System map + project scope | README + docs | ✅ |
| W2 | Requirements + eval + architecture | Requirements + evaluation criteria + v1 architecture + ADR | ✅ |