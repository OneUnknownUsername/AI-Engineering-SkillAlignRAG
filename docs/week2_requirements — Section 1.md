# Requirements Specification — SkillAlignRAG

Version: 1.0

## Section 1 — Functional Requirements (FR)

| \# | Requirement — The system SHALL | Scope Boundary — SHALL NOT (where relevant) |
| :---- | :---- | :---- |
| **FR1** | Ingest and index course documents from three distinct pedagogical evidence categories—Course Information PDFs (**CLO**), weekly lecture slide decks (**Taught**), and assessment rubrics (**Assessed**)—while preserving document provenance metadata (`course_code`, `evidence_level`, `doc_id`, and `page_or_slide_no`). | Ingest unverified external web content, student submissions, or course files lacking identifiable course and evidence-level metadata. |
| **FR2** | Evaluate a queried industry AI skill task against a selected SAIAH course separately across **CLO**, **Taught**, and **Assessed** evidence levels and classify coverage at each level as **Supported**, **Not Found** (documents available, no qualifying evidence identified), or **Insufficient Evidence** (required document category unavailable). | Conflate a missing document category (**Insufficient Evidence**) with confirmed skill absence (**Not Found**), or infer skill coverage from general parametric knowledge outside the uploaded course corpus. |
| **FR3** | Provide at least one verbatim supporting text span (`text_span`) together with its exact source document identifier and page or slide reference (`doc_id`, `page_or_slide_no`) for every evidence level classified as **Supported**. | Present fabricated, unverified, or non-verbatim quotes as source evidence, or cite evidence from one pedagogical level (e.g., lecture slides) to substantiate another level (e.g., assessment rubrics). |
| **FR4** | Decline queries that fall outside the defined SAIAH curriculum skill-alignment scope and return a clear scope-boundary notification redirecting the user to supported curriculum-audit tasks. | Automatically approve, rewrite, or submit official accreditation documents (`MQA-01`/`MQA-02`) or Senate curriculum papers, grade student work, evaluate individual lecturer performance, or provide general student advising. |
| **FR5** | Present skill-coverage audit results in a structured, side-by-side tabular summary across **CLO**, **Taught**, and **Assessed** levels formatted for curriculum review and Continual Quality Improvement (CQI) inspection by UTM lecturers and programme coordinators. | \- |

