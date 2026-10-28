# SkillAlign-RAG

## Local Ingestion And Retrieval Smoke Test

Use Python 3.12 (recommended) and select `.venv` as the VS Code interpreter.
Run commands from the repository root. VS Code launch configurations cover each stage.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m src.step0_normalize_formats
.venv/Scripts/python -m src.pipeline_a_course_ingestion
.venv/Scripts/python -m src.pipeline_b_indsf_skills --extract-only
```

Install LibreOffice and put `soffice` on PATH for PPTX/DOCX conversion. On Windows,
Microsoft Office plus `requirements-windows.txt` provides an optional COM fallback.
On Windows the console launcher `soffice.com` is preferred so conversion waits
for completion. An optional `outputs/tools/libreoffice_runtime.json` containing
`{"soffice_path": "absolute/path/to/soffice.com"}` selects a workspace-local
extracted LibreOffice runtime without a system installation.
Converted PDFs are cached under `outputs/normalized_pdf/`; source materials are
never modified. Pipeline A also runs normalization automatically. A failed or
stale conversion is logged and excluded, rather than treated as an empty folder.
The command writes all successfully parsed pages before returning a nonzero exit
code for document failures; `--allow-partial` explicitly permits a partial run.

The supplied locked 12-skill mapping is in `config/benchmark_skills.json`.
Pipeline B now runs two stages: B1 detects career roles and extracts tasks,
essential skills, competencies with SFIA levels, tools and Appendix A definitions
into `outputs/indsf_all_extracted_skills.json`. B2 filters senior/management and
nontechnical items, then retrieves the top evidence for S01-S12 using local dense
embeddings, IDF keyword matching and SFIA overlap. Input citation strings and
`config/benchmark_provenance.json` are not used. The
[configuration contract](config/README.md) describes the generated record format.
Compile the benchmark, then run:

```powershell
.venv/Scripts/python -m src.pipeline_b_indsf_skills --reuse-extraction
.venv/Scripts/python -m src.build_indexes
.venv/Scripts/python -m src.run_retrieval_smoke_test
.venv/Scripts/python -m src.validate_artifacts
.venv/Scripts/python -m pytest -q
```

`--extract-only` runs B1 without loading an embedding model. `--reuse-extraction`
rebuilds both stages from the existing parsed/OCR pages. B2 reuses the same cached
`BAAI/bge-small-en-v1.5` model as indexing; use `--offline` to require a cached
model. `--top-k` (default 3) and `--min-match-score` (default 0.30) control mapping.
`outputs/indsf_quality_report.md` reports role/section counts, duplicates, graduate
filtering and every generated source match. Empty matches are explicitly marked
`no_match`; similarity is evidence retrieval, not a coverage certification.
Downstream validation regenerates B1 and checks item IDs, source excerpts,
graduate eligibility, scores and definition/source fingerprints without a model.

All generated data, models, indexes, quality reports and retrieval logs go under
`outputs/` (gitignored). Source inputs remain untracked unless explicitly added.
The two existing HRD Corp filenames and the specification's canonical filenames
are recognized; ambiguous or missing benchmark PDFs are errors.

Local RapidOCR is enabled by default and uses bundled ONNX models. Use
`--disable-ocr` only for an explicitly native-only diagnostic run. Enable optional
vision descriptions with `--enable-vision-llm --vision-model qwen2.5vl:3b` on either
ingestion pipeline after starting Ollama and pulling that vision model. Ollama
must run on loopback. Unavailable Ollama is logged and extraction continues via
native text and OCR. Vision text is kept in `visual_diagram_summary` and never
enters the verbatim lookup. No answer-generation UI or NLI inference is included.
OCR uses a page render with native word regions masked, preserving native text
in its own field while recognizing new text in screenshots and diagrams.
Vision inference receives the original page image. Identical OCR images are
reused within a run. Sanitized
per-document extraction caches under `outputs/extraction_cache/` are keyed by
source content, extraction settings and parser revision, so interrupted runs can
reuse completed documents. Failed vision requests are retried on the next run.
For larger corpora, course ingestion accepts `--workers 2 --ocr-threads 8` to
use separate local extraction processes. Reduce these values on smaller CPUs.

The first dense indexing run downloads `BAAI/bge-small-en-v1.5` into
`outputs/models`; document text is embedded locally on CPU. Subsequent runs can
use `--offline`. Model download failures are errors. An explicit `--lexical-only`
indexing option supports offline BM25 diagnostics; reports label this mode and
do not describe it as hybrid retrieval. Both retrieval configurations use the
same page chunks and dense vectors. Routed Top-3 is per level; pooled Top-3 is
per course. Dense/BM25 weights are 0.5/0.5; catalog overlap adds up to 0.15 for
Taught candidates. Index manifests persist corpus fingerprints and reject stale
source artifacts. Embedding models may truncate pages beyond their token limit.

The lookup stores the whitespace-normalized, PII-redacted native/OCR union,
including pages excluded from indexing. Extracted Markdown tables are a separate
field to avoid representing table formatting as an exact native quote. OCR is
machine transcription and needs visual spot checks against source pages;
substring verification proves consistency with the extracted store. Redaction
logs contain types and offsets, not the original phone/email/room values.
PII detection is regex-based and does not claim to anonymize names or every
possible personal identifier.

CI/CLO documents force full-page RapidOCR and table extraction on every page.
Explicit CLO definition/header pages in lecture and assessment files gain
`auxiliary_evidence_levels: ["CLO"]` when the course has usable CI/CLO documents.
Their original `evidence_level`, page identity, and verbatim lookup remain intact;
the CLO route includes those pages while the pooled baseline stores them once.
Empty CI/CLO folders still cause missing-evidence abstention. Deck aspect cards
scan pages 1-6 for outcome, overview, outline, agenda, and numbered topic headings,
and trim trailing faculty/university footer lines. Room redaction requires an
explicit room/office label with a colon or hash, or an MJIIT room identifier.
Older cache pages with room redactions are reparsed from their PDF to recover
false positives; CI pages also bypass the older conditional-OCR cache.

`retrieval_smoke_test_report.md` and its JSON log cover 36 course/skill queries,
display per-level availability and score components, and flag potential pooled
level dilution. Retrieval candidates do not establish curriculum coverage.
Precision/recall/F1 and true retrieval accuracy require manually labeled
relevance judgements and are intentionally not fabricated by this smoke test.

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
