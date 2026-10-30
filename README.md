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
Explicit CLO definition/header pages in lecture files gain
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

## Step 2/5/6/7/8: local judgement and verified coverage audit

The runner consumes Pipeline A/B's `course_catalog_manifest.json`,
`industry_skills_benchmark.json`, `parsed_course_chunks.json`,
`verbatim_lookup_store.json`, and the shared `indexes/` artifacts. Build them
first using the ingestion, benchmark and index commands above. It does not
create substitute evidence when artifacts or models are unavailable.

Inside your university B200 `2g.45gb` Slurm allocation, activate a **Linux**
Python environment (the checked-in local `.venv` may be a Windows environment).
Install your university-supported B200 PyTorch CUDA build, then:

```bash
python -m pip install -r requirements-audit.txt
# Use your allocated scratch/project storage rather than a small HOME quota.
export HF_HOME=/path/to/your/scratch/huggingface
python -m src.run_skill_audit_pipeline --output-dir outputs
```

The default is Qwen2.5-14B in BF16 with greedy decoding, and DeBERTa-v3-large
NLI on `cuda:0`. Both load once. `device_map=auto` reserves GPU headroom but may
offload on a crowded allocation; the device map and actual available VRAM are
logged. Use `--llm-model Qwen/Qwen2.5-7B-Instruct` for the smaller LLM,
`--nli-model cross-encoder/nli-deberta-v3-base` for smaller NLI, or
`--cache-path /scratch/your/cache` if neither `HF_HOME` nor
`TRANSFORMERS_CACHE` is set. Environment cache settings take precedence.
`--offline` requires already-cached inference and embedding models.
Retrieval embeddings retain the existing `outputs/models` cache.

For an already-running local vLLM/Ollama OpenAI-compatible server:

```bash
python -m src.run_skill_audit_pipeline --backend openai_compat \
  --base-url http://localhost:8000/v1 --llm-model Qwen/Qwen2.5-14B-Instruct
```

For Ollama, use `http://localhost:11434/v1` and its actual installed model name.
The server must return JSON content and prompt/completion usage. NLI still runs
locally on CUDA; account for the server's VRAM usage on the same MIG slice.
The client accepts localhost endpoints only.

The completed run writes:

- `outputs/skill_coverage_audit_report.md`: three lecturer-facing S01–S12 tables.
- `outputs/skill_coverage_audit_results.json`: all 108 cells, candidates, raw
  classifications, exact canonical citations, rejection reasons, NLI scores,
  token usage, configuration, hardware and input fingerprints.
- `outputs/routed_vs_baseline_comparison_report.md`: counts, verification gates,
  latency percentiles, token totals, missing-document conflation and level
  omission diagnostics. Pooled baseline decisions remain unfiltered; its gates
  run retrospectively. Baseline per-cell timing/tokens are explicitly amortized
  over three levels; actual single-pass batch timing is also reported.
- `outputs/scope_and_abstention_safety_report.md`: 25 refusal cases, 12 valid
  queries, synthetic missing-folder cases, and actual missing manifest levels.

A checkpoint JSON is written after every completed course–skill pair for
inspection if interrupted; it is not automatically resumed. Malformed model
responses produce an explicit generation-error flag and no accepted citation.
Model execution failures stop the run rather than produce completed reports.
Gate 6B batches 2–4 atomic hypotheses per skill against both quote-only and
title-plus-quote premises. Both carry the factual `Course material:` source label
so NLI can resolve the hypothesis subject; this label does not assert skill support. It accepts maximum entailment ≥0.40, or ≥0.20 with
contradiction <0.15, non-contradiction ≥0.85 and at least two shared quote-domain
terms, after the pedagogical boundary checks. All fallback probabilities come
from the same winning pair. Every atomic score is retained in JSON. NLI
label order is read from the model config, never assumed. LLM candidate text is limited to 350 words and 1,800 characters; full
page/chunk text remains available to verification. CLO prompts start at the
extracted outcome table. Generation uses a compact classification/rank/quote
JSON schema (pooled levels use shorter classification/rank/quote arrays)
with 128 routed / 140 pooled token budgets, then restores document/page from the selected
rank into the full audit schema. Rationale is optional and at most 12 words.
Oversized NLI premises are rejected rather than silently truncating quotes.

Local inference API charge is reported as zero, excluding compute/electricity.
To calculate a cloud-equivalent estimate, pass both
`--input-usd-per-million` and `--output-usd-per-million` with your chosen
provider's rates. Without supplied rates the cloud estimate is “Not configured”.
Latency/cost targets are measured and reported, not presumed satisfied.
Observed routed/baseline differences require manual relevance review; they are
not ground-truth accuracy or recall measurements.

Run the controls without CUDA, dependencies or generated indexes:

```bash
python -m src.run_skill_audit_pipeline --safety-only
python -m unittest discover -s tests -p test_skill_audit.py -v
```

The integration test uses explicit model/retrieval doubles in a temporary
folder. It checks all 108 cells, baseline call accounting and missing-category
short-circuiting; it does not benchmark model quality or B200 latency.

Index rebuilds recompute auxiliary CLO memberships from physical source levels,
repairing legacy artifacts. Assessment documents can only enter Assessed or
pooled retrieval. CLO accepts official CI sources and explicit embedded lecture
CLOs when the CI folder is available; official outcome/synopsis pages rank first.
The new routing-policy version requires rebuilding older indexes. CI extraction
continues to use forced OCR plus native text and tables; the calibrated search
representation focuses on the extracted outcome section instead of staff metadata.

Gate 6A accepts normalized verbatim quote matches of at least 20 characters.
For 20–44 character seeds it prefers an enclosing sentence/bullet of at least
45 characters, but retains the exact seed if no suitable expansion exists.
The 45-character target is not a rejection threshold. It never pads a short
bullet with unrelated text. The quote must occur on the canonical lookup page
and within the matching retrieved chunk.

If a valid Top-3 citation points to the wrong page, Gate 6A checks the other
same-course, same-level candidates in that Top-3 list and corrects the rank,
document and page to the first verified match. It does not search the whole
lookup store, cross course/level boundaries, or repair paraphrased wording.
Original decisions stay unchanged in JSON; correction attempts and resolved
citation metadata are logged, and Gate 6B uses the resolved chunk's context.

S07's four atomic facets separately cover diagnosing overfitting, diagnosing
underfitting, applying regularization, and adjusting hyperparameters.

Local HF decoding stops at the first complete JSON object to prevent trailing
commentary or duplicate decisions when token budgets increase. Numbered task
boundaries are recognized even when PDF extraction flattens them onto one line.
