# Week 3 data inventory: SkillAlign-RAG

Pathway A (documents), with two branches. Generated from [`data/week3_manifest.json`](../data/week3_manifest.json), whose hashes the notebook verified.

All sources are real project data, not the synthetic practice pack.

## Requirements served

| Requirement | Data needed | Source |
| :--- | :--- | :--- |
| FR1 | Course documents by course and evidence category | SRC01–SRC38 |
| FR3 / RAI1 | Verbatim text with document and page reference | SRC01–SRC38 |
| FR7 | IndSF skill text and source references | SRC39–SRC40 |
| RAI2 | Which categories are missing or unprocessable | Folder status below |
| RAI3 | Personal data removed from extracted text | Redaction during preparation |
| NFR4 | Change detection per file | SHA-256 per source |

## Storage and access

| Data | Location | In public GitHub repo? |
| :--- | :--- | :--- |
| Raw course files | `data/courses/` | No: internal UTM material, kept in the author's local working copy |
| Prepared course records | `data/processed/prepared_text.jsonl`, `data/pipeline_v1/course_documents/` | No: holds full course text. Manifests and counts are published instead, as the lab allows |
| Raw IndSF PDFs | `data/industry_benchmark/` | Yes: not confidential per the project owner. Licence terms not verified |
| Prepared IndSF records | `data/processed/prepared_indsf_*.jsonl`, `data/pipeline_v1/indsf_documents/` | Yes |
| Manifests | `data/week3_manifest.json`, `data/pipeline_v1/*/pipeline_manifest.json` | Yes: hashes, counts and file names only |

File names of course documents appear in the public manifests. Earlier commits with these files remain reachable on GitHub by direct hash; the project owner accepted this.

## Known gaps and limits

- **SAIA2113 CLO:** the `01_CI_CLO` folder is empty, so 12 of the 108 coverage cells (the CLO cells for all 12 skills on this course) can only be Insufficient Evidence until a Course Information document is supplied.
- **Version and date:** not verified for any source. Dates in file names were not checked against the documents. A hash identifies the exact file, not its version or authority.
- **Permission:** a hash says nothing about permission to share. Course material permissions come from the lecturers and were not independently verified.
- **Names:** redaction covers email addresses, phone numbers and office rooms by regex. It does not detect names, so prepared course text must stay local.
- **Office files:** SRC07 (PPTX) and SRC09 (DOCX) were read through PDFs converted earlier on Windows, because LibreOffice was not yet installed on this node when the pipeline ran. The PDF hashes are recorded in the manifest.

## Inventory

Inspection evidence is the file's pages and prepared records, plus the first 12 characters of its SHA-256. Every source's page count equals its page-record count, and no page has empty text after OCR. SRC39 and SRC40 also produce 332 and 194 structured items, linked to their source in the manifest.

| Source ID | Filename | Type and purpose | Version / date / owner | Access / rights | Inspection evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| SRC01 | `SAIA1013_Responsible_AI_and_Ethics/01_CI_CLO/SAIA1013 Responsible AI and Ethics 2425-1.pdf` | PDF. Course Information: intended outcomes (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 3 pages, 3 records, `beb5792ca430` |
| SRC02 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Module 2 Additional Ethical Theories 11 Aug 2025.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 46 pages, 46 records, `f4018454e7f5` |
| SRC03 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Module 4 AI Ethics Risk Assessment.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 54 pages, 54 records, `b8500e5894c9` |
| SRC04 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Module 5  Ethics Centric in AI Design.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 56 pages, 56 records, `bdf412dedbba` |
| SRC05 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Module 6  AI Governance Sept.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 37 pages, 37 records, `7919e9d622c6` |
| SRC06 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Part 1 Module 3 Ethics From Religion Perspective.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 21 pages, 21 records, `8c85f6fb7f1f` |
| SRC07 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Part 2 Module 3 Ethics From Religion Perspective.pdf.pptx` | PPTX. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 59 pages, 59 records, `352a78f6ae36` |
| SRC08 | `SAIA1013_Responsible_AI_and_Ethics/02_Lecture_Slides_Taught/Week 1 Introduction to RAI and AI Ethics Class Notes.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 53 pages, 53 records, `8258d61d14e1` |
| SRC09 | `SAIA1013_Responsible_AI_and_Ethics/03_Assessments_Assessed/1-GROUP ASSIGNMENT SAIA 1013 RES AI ETHICS_3_24_25.docx` | DOCX. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 4 pages, 4 records, `e9211eac20a6` |
| SRC10 | `SAIA1013_Responsible_AI_and_Ethics/03_Assessments_Assessed/Assignment 3 (5%) Module 5.pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 1 pages, 1 records, `60516b878e19` |
| SRC11 | `SAIA1013_Responsible_AI_and_Ethics/03_Assessments_Assessed/SAIA 1013 Rubrics Assignment (5+5%).pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 1 pages, 1 records, `7bb369e747d9` |
| SRC12 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/WEEK 2 & 3 - UNDERSTANDING DATA TYPES AND PRE-PROCESSING.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 38 pages, 38 records, `184a865f7005` |
| SRC13 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 1 - INTRODUCTION TO ML.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 46 pages, 46 records, `9c9c3090a23e` |
| SRC14 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 10 Classification using Support Vector Machine.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 43 pages, 43 records, `24ed8fc11ca3` |
| SRC15 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 11 Classification using Decision Tree and Random Forest (2).pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 39 pages, 39 records, `cc2727916ddb` |
| SRC16 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 12 Classification using Artificial Neural Network (3).pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 72 pages, 72 records, `a6693bb8a5e9` |
| SRC17 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 13 Clustering.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 66 pages, 66 records, `de58300fd9d1` |
| SRC18 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 14 Ethical Consideration.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 69 pages, 69 records, `40ea912a62e1` |
| SRC19 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 4 - Supervised Learning.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 40 pages, 40 records, `4ba557440e34` |
| SRC20 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 5 - Unsupervised Learning.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 33 pages, 33 records, `7d5f34c7c8b9` |
| SRC21 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 6 - Model Evaluation.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 37 pages, 37 records, `4e6ddfa84663` |
| SRC22 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 7 - Linear Regression.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 48 pages, 48 records, `3cad947e677b` |
| SRC23 | `SAIA2113_Machine_Learning/02_Lecture_Slides_Taught/Week 9 Classification using Naive Bayes.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 32 pages, 32 records, `6b358b566991` |
| SRC24 | `SAIA2113_Machine_Learning/03_Assessments_Assessed/Assignment 1 - ML (12 Nov 2025).pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 7 pages, 7 records, `acd32dbb8f60` |
| SRC25 | `SAIA2113_Machine_Learning/03_Assessments_Assessed/SAIA 2113 - Machine Learning Project  Presentation SEM 1 20252026 (1).pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 5 pages, 5 records, `9c4410bc164f` |
| SRC26 | `SAIA2143_Data_Wrangling_and_Visualization/01_CI_CLO/CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf` | PDF. Course Information: intended outcomes (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 4 pages, 4 records, `1c85947fcf0d` |
| SRC27 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 1- Introduction to Data and Data Wrangling and Visualization.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 19 pages, 19 records, `48d99525fb8d` |
| SRC28 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 10-Ethics in Data Visualization.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 31 pages, 31 records, `fee75712835a` |
| SRC29 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 2-Identifying and Handling Missing Data with Spreadsheets-d.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 71 pages, 71 records, `b447f8f1493e` |
| SRC30 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 3-Dealing with Duplicates and Outliers D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 32 pages, 32 records, `c05096695965` |
| SRC31 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 4- Part 3 (Complete) for student.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 102 pages, 102 records, `145c7a647e66` |
| SRC32 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 5-Advanced Data Wrangling Techniques D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 50 pages, 50 records, `e6a1a016bfa7` |
| SRC33 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 6-Introduction to Data Visualization D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 60 pages, 60 records, `1e9f9436c39a` |
| SRC34 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 7-Data Visualization with Matplotlib and Seaborn D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 38 pages, 38 records, `d3ff988535f9` |
| SRC35 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 8-Interactive Data Visualization with Plotly D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 36 pages, 36 records, `d118095dc4f6` |
| SRC36 | `SAIA2143_Data_Wrangling_and_Visualization/02_Lecture_Slides_Taught/Topic 9-Introduction to Dashboards D.pdf` | PDF. Lecture slides: taught content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 38 pages, 38 records, `d879742d1e2a` |
| SRC37 | `SAIA2143_Data_Wrangling_and_Visualization/03_Assessments_Assessed/Group Assignment (30%) D UPDATED.pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 6 pages, 6 records, `4225b2debe06` |
| SRC38 | `SAIA2143_Data_Wrangling_and_Visualization/03_Assessments_Assessed/SAIA 2143 PMA (Question Paper) 05JAN2026 .pdf` | PDF. Assessment material: assessed content (FR1, FR3) | Version not verified; UTM Faculty of Artificial Intelligence (course teaching team) | Internal; local only | 10 pages, 10 records, `9413780861c4` |
| SRC39 | `HRD-Corp_IndSF_Artificial_Intelligence.pdf` | PDF. IndSF skill source text and references (FR7) | Version not verified; HRD Corp | Published framework; licence not verified | 28 pages, 28 records, `c1e65253310b` |
| SRC40 | `HRDCorp_IndSF_DataScience_2ndEdition.pdf` | PDF. IndSF skill source text and references (FR7) | Version not verified; HRD Corp | Published framework; licence not verified | 21 pages, 21 records, `03d9aca56d8b` |

## Representative inspection

The notebook's A2 cell lists every input file with its size. Its A3 and B3 cells show samples from two sources, including source hash, page count and text:

- **SAIA2113, `Week 13 Clustering.pdf`, page 9:** a lecture slide, with text readable after extraction.
- **HRD Corp IndSF AI, page 7:** a job description page, with text readable after extraction.
- **Structured IndSF items:** one job description task (page 3) and one competency (page 19), each with its role, section and source page.

File existence alone was not accepted as evidence: three committed files were found to be truncated, as described in the [pipeline decisions](week3_pipeline_decisions.md).
