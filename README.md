# SkillAlign-RAG

> A document-grounded AI assistant that helps UTM lecturers and programme coordinators verify industry skill coverage across course materials with page and slide citations.

## Problem Statement

Course lecturers struggle to manually verify whether specific industry skills are taught and assessed across dozens of scattered lecture slides, course information PDFs, and assessment rubrics. In the UTM SAIAH programme, this requires connecting course learning outcomes (CLOs), weekly teaching materials, and assessments across heterogeneous files. AI engineering offers a way to combine semantic retrieval, document provenance, and citation verification to produce evidence-backed skill-coverage judgements for CLOs, teaching, and assessment.

## Evidence of the Problem

- Curriculum alignment matters: Carnegie Mellon University's Eberly Center explains that misalignment between learning objectives, instruction, and assessment can undermine student motivation and learning. This supports the need to check whether stated skills are actually taught and assessed. [Source: Eberly Center, course alignment guidance](https://www.cmu.edu/teaching/assessment/basics/alignment.html).
- Malaysia's National AI Action Plan 2026-2030 identifies gaps in advanced AI talent and prioritises a talent pipeline from foundational AI literacy to specialist expertise. This provides national context for the project's focus on reviewing AI curriculum skills coverage. [Source: AI Nation 2030, Strategic Context and Foundational Enablers](https://ai.gov.my/aiactionplan2030/).

## Initial Related Work / Existing Approaches

The limitations below describe how each approach applies to the SkillAlign-RAG scope.

- **Manual curriculum mapping:** Lecturers compare learning objectives, teaching activities, and assessments to check alignment. **Key limitation:** Applying this process manually across dozens of PDFs and slide decks requires repeated document review. [Source: Eberly Center, course alignment guidance](https://www.cmu.edu/teaching/assessment/basics/alignment.html).
- **Keyword search (Ctrl+F):** Exact-term search helps locate explicit skill mentions. **Key limitation:** Different wording for the same concept can reduce recall, so academic terminology may not match an industry skill query. [Source: Manning, Raghavan, and Schutze, Introduction to Information Retrieval, Chapter 9](https://nlp.stanford.edu/IR-book/html/htmledition/relevance-feedback-and-query-expansion-1.html).
- **General-purpose LLMs / basic RAG:** Lewis et al. (2020) combine a generative model with retrieved passages to improve knowledge-intensive responses. **Key limitation for this project:** The original Wikipedia-based approach does not provide the course-specific page/slide tracking and explicit citation-verification workflow needed for skill-coverage auditing. [Source: Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401).

## Project Objectives

- O1: To design a document-ingestion and hybrid RAG pipeline that indexes UTM AI course documents (PDFs/PPTXs) with page and slide provenance.
- O2: To develop a retrieval solution with a citation-verification guardrail, using span matching and/or natural language inference (NLI), to classify skill coverage as **Supported** or **Insufficient Evidence** across CLOs, teaching materials, and assessments, without treating missing files as proof that a skill is absent.
- O3: To evaluate retrieval accuracy using Precision, Recall, and F1, citation faithfulness (groundedness), and query latency.

## Target Users

University course lecturers and programme coordinators, specifically those teaching or overseeing core courses in the UTM SAIAH programme, who need to audit industry skill coverage across course content.

## Data Sources

The following sources are planned in `week1_project_scope.md`. Specific document URLs were not supplied and will be added when the course materials and benchmark are selected.

- **Source 1: SAIAH course information (CI) PDFs** containing official CLOs, weekly schedules, and assessment breakdowns - URL: pending provision by the course team.
- **Source 2: Weekly lecture slides and assessment rubrics from three core SAIAH courses** providing evidence of skills taught and assessed - URL: pending provision by the course team.
- **Source 3: Industry skill benchmark** containing a curated list of 12-15 Malaysian AI industry skill tasks - URL: pending benchmark curation and source selection.

## Weekly Progress

| Week | Focus | Deliverable | Status |
|------|-------|-------------|--------|
| W1 | System map + project scope | README + docs | ✅ |
