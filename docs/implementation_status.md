# V1 implementation status

This is a documentation review of the checked-in source, not a claim that planned
acceptance tests have passed. [Requirements](week2_requirements.md) define the
target; [evaluation criteria](week2_evaluation_criteria.md) define how to test it.

| Requirement | What already exists | What still needs to be built |
| :--- | :--- | :--- |
| FR6 — Staff access | No application sign-in or account-role service. | A sign-in page, approved staff accounts/roles, and upload permission checks on the server as well as the screen. Signing in must not automatically grant staff privileges. |
| FR1 — Course uploads | Pipeline A reads course/category folders, converts PDF/PPTX/DOCX inputs, extracts text, and writes document outcomes and metadata. | Category upload controls, Submit, the approved-materials confirmation, alerts naming unsupported/failed files, and a visible document list. Unsupported extensions are currently skipped by normalization rather than reported to a user. |
| FR1 / FR2 — Automatic processing | Ingestion, index building, and auditing exist as separate commands. | Connect submission to processing, index refresh, and affected audit recalculation, with per-file and per-cell progress. Do not display old results as if they cover newly uploaded documents. |
| FR2 / FR5 — Dashboard | The batch runner produces all 108 results and side-by-side Markdown tables. | An interactive 36-row dashboard, course/skill/combined filters, clear-filter action, and evidence inspection controls. Filtering existing results should not run inference again. |
| FR7 — Default skills | Pipeline B generates S01–S12 definitions and source matches from the configured IndSF files. | Prepare/load the default benchmark without user setup and show names, descriptions, and generated source references. Report missing source matches honestly; do not substitute the ignored input citation strings. |
| FR2 / RAI2 — Progress and missing evidence | Backend helpers distinguish unavailable categories from processed categories; missing and processing-failed reasons already exist. | Show Pending/Processing and missing/failed explanations in the dashboard, and test transitions as uploads are processed. A generation/model failure must not silently become a completed Not Found result. |
| FR3 — CI authority | Only CI pages enter the CLO route, so a slide can no longer support CLO, and a missing CI gives Insufficient Evidence even when slides state CLOs. The audit report compares each slide outcome statement with the CI's numbered CLOs (repeats the CI, differs from the CI with both statements shown, not in the CI, or no CI) and lists slides that repeat the cited CI wording as corroboration. | Show the comparison and corroboration in the dashboard (FR5). Run the prepared CI-authority cases from the evaluation criteria at the evaluation stage. |
| FR4 — Supported selections | Course constants, a fixed benchmark runner, and an older keyword query guard exist. | Validate supported course and skill identifiers in the application/backend and display a scope message for invalid selections. The old query-refusal suite does not test this feature. |
| NFR4 — Small document updates | Extraction caches reuse unchanged documents. | Update changed evidence without rebuilding unrelated stores. `build_indexes.build()` currently re-embeds the full indexable corpus and rewrites all partitions. |
| NFR2 / RAI1 / RAI3 — Later evaluation stage | Tests, runtime/token logs, source verification, local-only model endpoints, and partial privacy controls exist. | At the later evaluation stage, run the labelled ground-truth evaluation, human citation review, upload/role/scope tests, and synthetic privacy/payload checks. These are planned validation activities, not missing product features or current blockers. |

Implementation references: [ingestion](../src/pipeline_a_course_ingestion.py),
[format handling](../src/step0_normalize_formats.py),
[benchmark preparation](../src/pipeline_b_indsf_skills.py),
[index building](../src/build_indexes.py),
[audit runner](../src/run_skill_audit_pipeline.py),
[citation verification](../src/citation_span_verifier.py),
[CLO routing](../src/curriculum_scope.py), and
[scope/abstention](../src/scope_and_abstention_control.py).

The dashboard will use a FastAPI backend, which checks sign-in and the user's
role on every request so that direct backend requests cannot bypass FR6, and a
React front end. The backend and front end will run on the
university GPU node next to model inference (B200 allocation, inside a Slurm job
started through Open OnDemand), so the backend reaches the models over localhost,
as the existing localhost-only model client requires. The dashboard is viewed in
a laptop browser through VS Code tunnel port forwarding, which only the signed-in
developer can open; the traffic is encrypted and relayed by Microsoft's tunnel
service. Lecturers see the dashboard in on-screen demonstrations rather than
through their own access. It is reachable only while the job runs, and the
laptop does not need to run the models.

Latency and cost must distinguish a single evidence-level evaluation from a full
three-level course–skill audit and a full 108-cell refresh. The current comparison
report normalizes cost per 100 cells; the requirement is per 100 full skill audits
(300 cells). The planned benchmark should report the latter explicitly. Loading
or filtering saved dashboard results is a separate UI operation, not an audit
inference measurement.
