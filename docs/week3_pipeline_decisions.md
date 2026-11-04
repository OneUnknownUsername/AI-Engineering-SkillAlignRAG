# Week 3 pipeline decisions: SkillAlign-RAG

Evidence comes from the executed [notebook](../notebooks/week3_pipeline.ipynb) unless stated otherwise. The pipeline is [`src/week3_pipeline.py`](../src/week3_pipeline.py), which calls the existing extractors without changing them. The workflow is in the [pipeline diagram](week3_pipeline_diagram.png), with an [editable Draw.io version](week3_pipeline_diagram.drawio).

## Summary

| Item | Decision |
| :--- | :--- |
| Requirements | FR1, FR3, FR7, RAI1, RAI2, RAI3, NFR4 |
| Sources | 38 course documents (1,407 pages) and 2 IndSF PDFs (49 pages) |
| Pathway | A (documents), two branches. PPTX and DOCX are converted to PDF first |
| Preparation | One record per page; native text plus RapidOCR; regex PII redaction |
| Output | Page records for both branches, plus 526 structured IndSF items |
| Output location | Part B: `data/processed/`, with lineage in `data/week3_manifest.json`. Part C: `data/pipeline_v1/course_documents/` and `data/pipeline_v1/indsf_documents/`. Prepared course text (`prepared_text.jsonl` in both locations) stays local and is not in the public repository |
| Stops at | Prepared data. Embeddings, indexes and model judgement are later stages |
| Runs on | Local notebook on the university node, CPU only |

The lecturer confirmed that code may differ from the lab if the deliverables are submitted. The lab's Colab cells are replaced by the existing extractors, while the lab's stages, manifests and repeatability check are kept.

## Part B comparisons

Both comparisons use the same 1,407 course pages.

### Decision 1: page-level records

| Approach | Chunks | Median chars | Max chars | End mid-word | Span several pages | Record a page reference |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Page-level (selected)** | 1,407 | 427 | 7,714 | 0 | 0 | 1,407 |
| Lab fixed, 500 characters | 1,525 | 500 | 500 | 990 | 1,062 | 0 |
| Lab paragraph-aware, 500 characters | 1,525 | 500 | 500 | 990 | 1,062 | 0 |

- **Benefit:** every record keeps an exact page, which FR3 and RAI1 require. The lab's splitters record `page: None`, and 1,062 of their 1,525 chunks (70%) span more than one page, so a single page could not be assigned to them.
- **Accepted limitation:** page sizes vary widely. 21 pages exceed 2,000 characters and the longest has 7,714, so an embedding model may truncate long pages. A page can also split one idea across two records.
- **Identical lab results:** the two lab approaches behave the same here because the text cleaning removes blank lines, leaving the paragraph splitter nothing to split on. This does not show that paragraph-aware chunking is equivalent on text that keeps its blank lines.
- **"End mid-word" is a heuristic:** it counts chunks whose boundary falls between two letters or digits.

### Decision 2: native text plus OCR

| Approach | Total words | Pages with no text | Pages under 4 words |
| :--- | ---: | ---: | ---: |
| Native text only | 81,750 | 7 | 64 |
| **Native + RapidOCR (selected)** | 107,590 | 0 | 7 |

- **Benefit:** OCR adds 25,840 words (32%) from screenshots and diagrams, and leaves no page empty. Without it, that text could not be retrieved or cited.
- **Accepted limitation:** OCR is machine transcription, and this comparison measures how much text it adds, not how accurate that text is. Quotes that rely on OCR need visual spot checks.

Missing values are not imputed. Non-indexable pages (31 course pages, such as dividers) keep their text so that citation lookup stays complete.

## ETL and batch

- **ETL, not ELT:** redaction and provenance must be applied before data reaches any later stage, so transformation happens before storage. Raw files are kept unmodified.
- **Batch, not streaming:** course files change occasionally and arrive as whole documents. Each run processes a complete, fixed set of files.
- **Later work:** FR1 expects processing to start from a staff upload. That trigger and NFR4's incremental update are not built or tested here. This pipeline disables the document cache and re-extracts everything, on purpose, so the repeatability check is real.

## Stage contracts

| Stage | Contract | Evidence | Failure response |
| :--- | :--- | :--- | :--- |
| Ingest | Sources exist, are complete, and convert or open | 40 of 40 files pass integrity checks | Stop and name the file |
| Inspect | Pages, formats, levels and folder status are readable | Inspection block in each manifest | Stop on failed documents; report empty folders as known gaps |
| Prepare | One record per page, with source identity and redaction | 1,407 + 49 page records, 526 items | Stop on extraction failure |
| Validate | Non-empty, read-back equal, unique IDs, valid pages, records match pages, no PII patterns remain | All pass; 0 email, phone or room matches | Stop and report the rule that failed |
| Record lineage | Each source links to its output by SHA-256 | 40 lineage records verified | Stop on a missing file or mismatch |

Both diagram failure points were tested on temporary synthetic files in the notebook. A truncated PDF stopped at ingest, and a changed output stopped at record lineage.

## Repeatability

| Check | Result |
| :--- | :--- |
| Rerun on the same machine, no cache, both branches | Sources, outputs and mappings identical |
| Part B output against Part C output | All three prepared files identical |

**This is a repeatability smoke test on one machine, not cross-environment reproducibility.** Compared with the earlier Windows run in `outputs/`, a separate check found:

- All 1,407 page IDs and indexable flags are the same.
- **432 pages have different text**, all of them lecture slides.
- Among those, median similarity is 98%, 39 pages fall below 90%, and the lowest is 32%.

The cause has not been established. The two runs differ in operating system and possibly in library versions. Existing indexes and audit results under `outputs/` were built from the earlier text, so they should be rebuilt from one consistent run before the Week 2 evaluation relies on them.

## Provenance and access caveats

- **Truncated files found and fixed:** the pipeline run revealed three truncated files in the latest commit: one PPTX, one lecture PDF and the IndSF Data Science PDF. The IndSF PDF still opened as 21 pages, but 12 pages that have text in the intact file came out empty. Intact versions were restored from the repository's own history, and hash checks against the extraction cache show that earlier outputs used the intact PDFs. The ingest integrity check was added as a result, and it detects all three damaged files.
- **Office conversion was not exercised:** the PPTX and DOCX were read through PDFs converted earlier, because LibreOffice is not installed on this node. Without those PDFs, a run stops at ingest and names the file.
- **Code version:** manifests record commit `8507604`, the base commit. `src/week3_pipeline.py` was not yet committed when the notebook ran, so the commit that adds it is the one to read alongside these results.
- **Saved notebook output:** repeated ONNX Runtime thread warnings were removed from the saved output, and the final artefact-listing cell was refreshed after the ignore rules changed. Neither affects any result.
- **What hashes do not show:** data quality, source authority or permission to share. Source version and access rights are marked as not verified in the manifests. Fuller review belongs to Topic 4.
- **Privacy:** redaction is regex-based and does not detect names. Prepared course records stay out of the public repository, and the [data inventory](week3_data_inventory.md) records where each dataset is stored.

## Later measures this affects

From the [evaluation criteria](week2_evaluation_criteria.md):

- **Provenance Schema Completeness:** page records carry document, page, course and level.
- **Source Citation Faithfulness and Verbatim Support:** depends on the page text, including OCR accuracy.
- **Missing-Evidence Abstention and Audit-State Clarity:** depends on the folder status, including the SAIA2113 CLO gap.
- **Isolated Course-Document Updates:** per-file hashes support this later, but it is not tested yet.
