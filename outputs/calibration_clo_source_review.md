# Calibration and CLO source review

Both official CI documents already had native text, forced OCR, and indexed CLO tables on PDF page 1. The old ranking mixed primary and auxiliary pages without a source priority; exam pages were also admitted by the auxiliary CLO rule. The new index ranks official commitment pages first and removes assessment memberships from CLO/Taught.

Old indexed assessment pages with auxiliary CLO membership: 2. Current CLO/Taught partitions contain zero assessment pages.

| Course / skill | Previous CLO Top-3 | Rebuilt CLO Top-3 |
| --- | --- | --- |
| SAIA1013 / S08 | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p2 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p2 (Taught)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p3 (Taught) | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p1 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p2 (Taught)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p3 (Taught) |
| SAIA1013 / S09 | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p2 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p3 (Taught)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p2 (Taught) | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p1 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p2 (Taught)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p3 (Taught) |
| SAIA1013 / S10 | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p2 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p5 (Taught)<br>SAIA1013 Responsible AI and Ethics 2425-1.pdf, p3 (CLO) | SAIA1013 Responsible AI and Ethics 2425-1.pdf, p1 (CLO)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p5 (Taught)<br>Week 1 Introduction to RAI and AI Ethics Class Notes.pdf, p2 (Taught) |
| SAIA2143 / S01 | SAIA 2143 PMA (Question Paper) 05JAN2026 .pdf, p3 (Assessed)<br>Topic 3-Dealing with Duplicates and Outliers D.pdf, p2 (Taught)<br>Topic 5-Advanced Data Wrangling Techniques D.pdf, p2 (Taught) | CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf, p1 (CLO)<br>Topic 3-Dealing with Duplicates and Outliers D.pdf, p2 (Taught)<br>Topic 5-Advanced Data Wrangling Techniques D.pdf, p2 (Taught) |
| SAIA2143 / S02 | Topic 5-Advanced Data Wrangling Techniques D.pdf, p2 (Taught)<br>SAIA 2143 PMA (Question Paper) 05JAN2026 .pdf, p3 (Assessed)<br>Topic 3-Dealing with Duplicates and Outliers D.pdf, p2 (Taught) | CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf, p1 (CLO)<br>Topic 5-Advanced Data Wrangling Techniques D.pdf, p2 (Taught)<br>Topic 3-Dealing with Duplicates and Outliers D.pdf, p2 (Taught) |
| SAIA2143 / S03 | Topic 9-Introduction to Dashboards D.pdf, p2 (Taught)<br>Topic 6-Introduction to Data Visualization D.pdf, p2 (Taught)<br>Topic 7-Data Visualization with Matplotlib and Seaborn D.pdf, p2 (Taught) | CI SAIA 2143 Data Wrangling and Visualization 202526 Sem 1.pdf, p1 (CLO)<br>Topic 9-Introduction to Dashboards D.pdf, p2 (Taught)<br>Topic 6-Introduction to Data Visualization D.pdf, p2 (Taught) |

All six affected queries now rank the official CI PDF page 1 first. This verifies source/ranking repair; supported coverage still requires the LLM and both verification gates.

## Final B200 rerun

Completed all 108 cells and 36 pooled calls. Routed p90 decreased from 4499.3 ms to 1027.0 ms. Gate 6A accepted 25 quotes and rejected 4; Gate 6B accepted 24 and rejected 1. Every accepted citation was rechecked as an exact canonical lookup-page substring. No assessment source enters CLO/Taught partitions. All available S11/S12 cells are Not Found; all 12 SAIA2113 CLO cells abstain without inference.

Two routed generations returned quotes below the 40-character minimum; one pooled generation was truncated at 96 tokens. These fail closed and remain generation-error flags requiring review. No citation from these errors was accepted.

The NLI premise uses a factual Course material: provenance label on both quote-only and title-plus-quote variants. The label does not assert skill support. Atomic scores and the exact acceptance rule are logged per cell.
