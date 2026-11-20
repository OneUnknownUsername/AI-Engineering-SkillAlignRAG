# Week 4 Data Quality & Bias Report: SkillAlign-RAG

Audit date: 2026-11-20. Labels: **Observed**, **Inferred risk**, **N.V.** (Not Verified). Evidence: [`src/week4_audit_checks.py`](../src/week4_audit_checks.py) (read-only; prints counts and identifiers only) and the manual sample check in [Appendix A](#appendix-a-audit-sample). No course text is quoted, because the repository is public.

## 1. Project and Data Overview

| Field | Response / evidence |
| :--- | :--- |
| Purpose | SkillAlign-RAG helps UTM SAIAH lecturers and programme coordinators see whether 12 HRD Corp IndSF-derived skills are Supported, Not Found or Insufficient Evidence at the CLO, Taught and Assessed levels of 3 courses. |
| Requirements | **FR3 / RAI1:** every Supported result cites a verbatim span with `doc_id` and page, so the page text must be faithful and the identifiers correct. **RAI2:** Insufficient Evidence must be kept apart from Not Found, so the data must show which course × level categories have processable records. |
| Pathway and output | Pathway A, course documents only (36 PDF, 1 PPTX, 1 DOCX). Topic 3 **Part C** output `data/pipeline_v1/course_documents/prepared_text.jsonl`, traced with its [`pipeline_manifest.json`](../data/pipeline_v1/course_documents/pipeline_manifest.json). The audited run is from 2026-11-06 (commit `7ffc49d`, SHA-256 `77a78dddca46…`); it was regenerated after the fix in Section 7. The output holds course text, so it is kept locally and not published. |
| Source and access | SRC01–SRC38 ([Week 3 inventory](week3_data_inventory.md)), owned by the UTM FAI course teaching teams. Version: N.V. Use was permitted in person by the Head of the Intelligence and Informatics Department; written permission is N.V. **Observed:** all 38 local files match their manifest hashes. |
| Population and sample | 1,407 page records (1,376 indexable). Unit: one page record. Sample: 15 records (S01–S15), chosen purposively across the 8 course × level cells that hold data plus known risk cases (OCR-only, converted PPTX/DOCX, repeated, short, skipped, redacted, exam paper). Limitation: the sample is not random, so it cannot give a dataset-wide error rate. |

**Checkpoint A1:** SAIA2113 has no Course Information document, so FR3 cannot cite CLO evidence for it and RAI2 must show Insufficient Evidence for 12 of the 108 cells.

## 2. Five-Dimension Quality Scorecard

| Dimension | Finding | Evidence | Impact | Decision |
| :--- | :--- | :--- | :--- | :--- |
| Completeness | **Observed:** SAIA2113 CLO has 0 records (empty folder). Every other cell has at least 3 indexable records. | Appendix B; manifest `known_gaps` | 12 CLO cells can only be Insufficient Evidence. This is a documented gap, not a defect. | Warning |
| Consistency | **Observed:** for the converted SRC07 and SRC09 (63 records), `doc_id` names the converted PDF (`….pdf.pdf`), not the uploaded file. | `doc_id` vs `source` check; S03, S06 | **Inferred risk:** FR3 citations name a file the uploader never supplied. | Warning |
| Accuracy | **Observed:** all 15 sampled records keep their page's words. 3 have defects: merged OCR words and lost diagram order (S07), stray OCR characters (S06), and table rows flattened in `text` (S01, S02). For S01, `tables_markdown` keeps the CLO rows correct. | Manual page comparison (Appendix A) | **Inferred risk:** RAI1's substring check may fail on OCR text (7 OCR-only and 1,198 merged native + OCR records). Population error rate: N.V. | Warning |
| Timeliness | **Observed:** the SAIA1013 CI is for session 2024/25, while its slides and assignment date from Aug–Sep 2025. The SAIA2143 CI (2025/26) matches its exam date. Versions: N.V. | S01, S03; file names | **Inferred risk:** SAIA1013 CLO results may be judged against an earlier offering's outcomes. | Review |
| Uniqueness | **Observed:** no duplicate `record_id` or (`doc_id`, page). 35 indexable records in 7 SAIA2113 decks repeat another page of the same deck (outline slides; one is repeated 9 times, S08). | Appendix B; S08 | **Inferred risk:** repeated outlines may crowd top-k retrieval. They are real slides, so they are kept. | Warning |

## 3. Validation Findings

| Rule | Risk / requirement | Condition and scope | Result | Decision |
| :--- | :--- | :--- | :--- | :--- |
| V1 | A Supported claim cannot be traced to a page (FR3, RAI1) | All 1,407 records. Each record needs non-empty `doc_id` and text; `page` within the source's page count (`data/week3_manifest.json`); a valid `course_code` and `evidence_level`; and `source_sha256` equal to its manifest entry. | **Observed:** 1,407 pass, 0 fail | Pass. A failure would be a **hard fail**, fixed in the pipeline and never by deleting the page. |
| V2 | A missing category is reported as Not Found (RAI2) | 9 course × level cells. Each needs ≥ 1 indexable record or must be listed in manifest `known_gaps`. | **Observed:** 8 pass; 1 documented gap (SAIA2113 CLO); 0 undocumented | Review → **exception, not a defect.** Keep it as Insufficient Evidence and do not fill it from slides. |

An undocumented gap would be a hard fail. **Additional check:** residual phone numbers. A widened pattern found **10 matches in 2 records** (CI p1 of SAIA1013 and SAIA2143; 5 numbers, each in both `text` and `tables_markdown`) and none elsewhere. Defect → fixed (Section 7).

## 4. Duplicate, Anomaly and Coverage Findings

- **Duplicates:** see Uniqueness above. Repeats across documents are only closing slides, which are already skipped.
- **Pipeline-induced loss:** the 31 skipped pages are 21 closing slides, 8 "Knowledge Check" titles and 2 class-activity questions. No teaching content was lost. **Observed** from the text of all 31 skipped pages.
- **Anomalies:** listed in [Appendix C](#appendix-c-anomalies-and-fix-record). One is a `printed_slide_no` that holds a table total; citations use `page`, so they are unaffected.

| Category | Expected | Observed / gap | Possible effect |
| :--- | :--- | :--- | :--- |
| CLO evidence per course | One CI per course | SAIA1013: 1 document (3 pages); SAIA2143: 1 document (4 pages); SAIA2113: none. CLO is 7 of 1,407 records. | 12 cells Insufficient Evidence; 24 cells each depend on 3–4 pages (**inferred risk**) |
| Malay-language teaching | Content retrievable by English skill descriptions | 50 Malay-majority records, all from SRC07: 15% of SAIA1013 Taught, 0 in other courses. Method: function-word count; S06 checked by hand. | Skills taught in that module may come out Not Found (**inferred risk**) |

Limits: the language label is a heuristic (31 records undetermined). Skill-level coverage needs the ground-truth labels, so it is left for evaluation.

## 5. Bias Assessment

**Representation bias (language) with a pipeline-induced measurement part. Inferred risk, not proven unfairness.**

- **Source decision:** one SAIA1013 module (SRC07) is in Malay, while the 12 skills are in English. The default RapidOCR models are not built for Malay; on S06 they added a stray non-Latin character.
- **Gap:** 50 records (3.6%), in one course and one level.
- **Effect:** English queries may rank Malay evidence lower, so that course's Taught cells could be marked Not Found. That is the unfair-evaluation risk RAI2 guards against, and it would lower Taught recall (NFR2).
- **Control:** tag each record's language; include Malay pages in the ground truth; report Taught recall separately for Malay and English pages; add Malay query variants if a gap appears.

## 6. Privacy, Rights and Governance

| Question | Finding |
| :--- | :--- |
| Provenance | SHA-256 for every source in the manifest; 38/38 match. Versions N.V. |
| Rights | Use permitted in person; written record N.V. Redistribution not permitted, so raw files, prepared course records and `outputs/` are gitignored, and only manifests, counts and hashes are public. **Observed:** older commits holding course files were removed via GitHub Support (checked 2026-11-13). |
| Privacy | **Observed:** CI staff tables and title slides hold staff names, emails, phones and office locations, none of which the task needs. Emails were redacted, but **5 phone numbers were missed** (fixed). Names are not redacted (known limit), and office-location fragments remain in the two CI tables. No student data was seen (S04's name and matric fields are blank). SRC38 is an exam paper, kept local. |
| Consent / basis | No student data, so consent does not apply. Staff details are incidental in faculty documents provided for curriculum review. |
| Model use (RAI3) | **Observed:** model calls are limited in code to local inference ([`src/llm_judgement_service.py:108-111`](../src/llm_judgement_service.py#L108-L111)). Network-payload test: N.V. (later evaluation). |
| Maintenance | The author maintains the pipeline and patterns; coordinators supply documents each semester. Revalidate on any hash change, new CI, code change or new semester. |

**Safeguards:** the phone pattern was widened, with regression tests (done); downstream artefacts are to be rebuilt (Section 7).

## 7. Mitigation and Impact on Requirements

**Done:** the redaction fix in `src/extraction.py` was revalidated: 0 residual phone matches, and only the 2 CI records changed ([Appendix C](#appendix-c-anomalies-and-fix-record)).

| Priority improvement | Who / when | Requirements | Remaining risk |
| :--- | :--- | :--- | :--- |
| 1. Rebuild the Pipeline A artefacts in `outputs/` (chunks, lookup, indexes, results, dashboard); they still hold the 5 numbers. Review office-location fragments at the same time. | Author, before the next evaluation run | RAI3, RAI1 | Names stay unredacted; the files stay local |
| 2. Obtain the SAIA2113 CI and confirm which SAIA1013 CI applies to 2025/26. | Author with course coordinators, before ground-truth evaluation | FR3, RAI2, FR2, NFR2 | The 12 SAIA2113 cells stay Insufficient Evidence until it arrives |

Also during evaluation: the Malay coverage check (Section 5), and collapsing repeated outlines if they crowd top-k.

## 8. Quality-Gate Decision

**GO WITH CONDITIONS** for the regenerated Part C course-document output, for local use in V1 retrieval and evaluation, not for publication.

**Evidence:**
- V1: 1,407/1,407 records pass, and 38/38 source hashes match.
- V2: 8/9 cells have evidence, plus one documented gap.
- 15/15 sampled pages keep their words.
- The one privacy defect found was fixed and revalidated.

**Conditions:**
1. SAIA2113 CLO is shown as Insufficient Evidence until a CI is supplied.
2. `outputs/` is rebuilt before results are reported.
3. Prepared course text stays local.

**Residual risks:** unredacted names, OCR errors, possible under-retrieval of Malay content, and unverified versions and permission.

**Re-review triggers:** a source hash change or new upload; a new or replaced CI; an extraction or redaction code change; citation faithfulness below 95% or lower recall on Malay pages during evaluation.

---

## Appendix A: Audit sample

Each sampled page was rendered from its source file (from the converted PDF, with a recorded hash, for S03 and S06) and compared by eye with the record's `text` field on 2026-11-20. Item IDs follow the order of the rules in the check script.

| ID | Why selected | Course / level | Document, page | Spot-check result |
| :--- | :--- | :--- | :--- | :--- |
| S01 | CI with redaction | SAIA1013 / CLO | `SAIA1013 Responsible AI and Ethics 2425-1.pdf` p1 | Words present; table rows interleaved in `text`, CLO rows correct in `tables_markdown`; 2 phone numbers not redacted |
| S02 | CI | SAIA2143 / CLO | `CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf` p2 | Words present; table rows interleaved; `printed_slide_no` = table total |
| S03 | Converted DOCX | SAIA1013 / Assessed | `1-GROUP ASSIGNMENT SAIA 1013 RES AI ETHICS_3_24_25` p1 | Matches |
| S04 | Assignment | SAIA2113 / Assessed | `Assignment 1 - ML (12 Nov 2025).pdf` p1 | Matches |
| S05 | Exam paper | SAIA2143 / Assessed | `SAIA 2143 PMA (Question Paper) 05JAN2026 .pdf` p2 | Matches |
| S06 | Converted PPTX | SAIA1013 / Taught | `Part 2 Module 3 Ethics From Religion Perspective` p10 | Matches, plus 2 stray OCR characters |
| S07 | OCR-only page | SAIA1013 / Taught | `Module 2 Additional Ethical Theories 11 Aug 2025.pdf` p35 | Words present; merged words, I/l confusion, diagram order lost |
| S08 | Repeated page | SAIA2113 / Taught | `Week 4 - Supervised Learning.pdf` p5 | Matches |
| S09 | Inspected in Week 3 | SAIA2113 / Taught | `Week 13 Clustering.pdf` p9 | Matches (superscript in O(n²) becomes "n2") |
| S10 | Long OCR deck | SAIA2143 / Taught | `Topic 4- Part 3 (Complete) for student.pdf` p50 | Matches |
| S11 | Short indexable page | SAIA1013 / Taught | `Module 4 AI Ethics Risk Assessment.pdf` p20 | Matches (section title slide) |
| S12 | Skipped: activity_without_explanation | SAIA1013 / Taught | `Week 1 Introduction to RAI and AI Ethics Class Notes.pdf` p52 | Matches; a closing slide, so skipping is right although the reason label does not describe it |
| S13 | Skipped: divider | SAIA2113 / Taught | `WEEK 2 & 3 - UNDERSTANDING DATA TYPES AND PRE-PROCESSING.pdf` p38 | Matches; closing slide, correctly skipped |
| S14 | Auxiliary CLO tag | SAIA1013 / Taught | `Week 1 Introduction to RAI and AI Ethics Class Notes.pdf` p2 | Matches |
| S15 | Redaction | SAIA2143 / Taught | `Topic 1- Introduction to Data and Data Wrangling and Visualization.pdf` p1 | Matches; email redacted, lecturer name kept (known limit) |

## Appendix B: Check output

`python -m src.week4_audit_checks`, run 2026-11-20 (sample listing omitted; see Appendix A):

```text
== Population
output sha256 matches manifest: True
records: 1407 | indexable: 1376
sources in manifest: 38
  SAIA1013 CLO: 3 records, 3 indexable, folder available
  SAIA1013 Taught: 326 records, 325 indexable, folder available
  SAIA1013 Assessed: 6 records, 6 indexable, folder available
  SAIA2113 CLO: 0 records, 0 indexable, folder folder_empty_or_missing
  SAIA2113 Taught: 563 records, 551 indexable, folder available
  SAIA2113 Assessed: 12 records, 12 indexable, folder available
  SAIA2143 CLO: 4 records, 4 indexable, folder available
  SAIA2143 Taught: 477 records, 459 indexable, folder available
  SAIA2143 Assessed: 16 records, 16 indexable, folder available
== Raw source hashes (local working copy only)
sources: 38 | missing: 0 | hash mismatch: 0
== Uniqueness
duplicate record_id: 0 | duplicate (doc_id, page): 0
exact repeated-text groups: 13 | records in them: 47
  within one document: 8 groups; 35 indexable records in 7 documents {'SAIA2113': 35}
  across documents: 5 groups; indexable records in them: 0
== Consistency: printed_slide_no vs PDF page
{'none': 625, 'equal': 489, 'differs': 293}
skip reasons: {'activity_without_explanation': 28, 'divider': 3}
extraction methods: {'native_text+rapidocr': 1198, 'native_text': 202, 'rapidocr': 7}
```

`python -m src.week4_audit_checks --part b --output <audited copy> --manifest <audited manifest>`. This is the 2026-11-06 run, kept as a local copy before the fix:

```text
== V1 citation fields (all records)
tested: 1407 | passed: 1407 | failed: 0
failures by condition: {'doc_id': 0, 'text': 0, 'page': 0, 'course_code': 0, 'evidence_level': 0, 'source_sha256': 0}
== V2 category availability (9 course x level cells)
  SAIA2113 CLO: 0 indexable records -> documented gap (review); manifest status: folder_empty_or_missing
result: {'pass': 8, 'documented gap (review)': 1}
== Coverage: records by level
{'CLO': 7, 'Taught': 1366, 'Assessed': 34}
documents by level: {'Taught': 29, 'Assessed': 7, 'CLO': 2}
== Coverage: language (Malay vs English function-word count per record)
  SAIA1013 Assessed english 6
  SAIA1013 CLO english 3
  SAIA1013 Taught english 264
  SAIA1013 Taught malay 50
  SAIA1013 Taught undetermined 12
  SAIA2113 Assessed english 12
  SAIA2113 Taught english 550
  SAIA2113 Taught undetermined 13
  SAIA2143 Assessed english 16
  SAIA2143 CLO english 4
  SAIA2143 Taught english 471
  SAIA2143 Taught undetermined 6
  Malay-majority document: Part 2 Module 3 Ethics From Religion Perspective.pdf.pdf {'malay': 50, 'english': 2, 'undetermined': 7}
== Pipeline-induced loss: skipped pages by content
{'closing (thank you)': 21, 'class activity question': 2, 'knowledge check title': 8}
== Residual phone pattern (current src.extraction pattern)
matches: 10 | records: 2
  CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf p1 tables_markdown: 3
  CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf p1 text: 3
  SAIA1013 Responsible AI and Ethics 2425-1.pdf p1 tables_markdown: 2
  SAIA1013 Responsible AI and Ethics 2425-1.pdf p1 text: 2
```

After the fix and re-run (`python -m src.week4_audit_checks --part b`), V1 and V2 output is unchanged and the last check reads:

```text
== Residual phone pattern (current src.extraction pattern)
matches: 0 | records: 0
```

## Appendix C: Anomalies and fix record

**Anomalies (Observed, none of which blocks use):**
- S02: `printed_slide_no` holds a table total ("74"). Citations use the PDF `page` field, which is correct.
- 18 closing slides carry the skip reason `activity_without_explanation`. Skipping them is correct; the label is misleading.
- SRC07 and SRC09: `doc_id` names the converted PDF (Section 2, Consistency).
- OCR artefacts in S06 and S07 (Appendix A).

**Redaction fix (2026-11-20):**
- **Change:** the phone pattern in [`src/extraction.py`](../src/extraction.py) now also matches landlines, the 60/+60 prefix with or without "+", and an OCR'd "O" for the leading zero. Two regression tests were added to [`tests/test_pipeline.py`](../tests/test_pipeline.py), one for the new formats and one for teaching-content numbers that must stay unchanged; the full suite passes.
- **Check before re-running:** the new pattern was run over the audited output. It matched exactly the 10 missed occurrences and nothing else among the 1,407 records.
- **Re-run:** the course branch was re-run (`--kind course_documents --repeat`) and the repeat check passed.
- **What changed:** still 1,407 records; exactly 2 changed (SAIA1013 CI p1 and SAIA2143 CI p1), only in `text`, `tables_markdown` and `redaction_count`.
- **Counts:** phone redaction events rose from 9 to 23. The manifest counts these per extraction pass, so the number is not 10.
- **Revalidation:** the residual check now finds 0 phone matches, and V1 and V2 results are unchanged.
- **New output:** SHA-256 `9518eea9313a…`.

**Week 3 records brought up to date (2026-11-20):** the Week 3 notebook was re-executed, which regenerated:
- the Part B copy (`data/processed/`);
- `data/week3_manifest.json`;
- both Part C branches.

All three course outputs now carry SHA-256 `9518eea9313a…`. The repeatability check passed. The IndSF branch also redacted 2 occurrences of the publisher's office phone number.
