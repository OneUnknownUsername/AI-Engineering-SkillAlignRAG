# V1 implementation status

This is a documentation review of the checked-in source, not a claim that planned
acceptance tests have passed. [Requirements](week2_requirements.md) define the
target; [evaluation criteria](week2_evaluation_criteria.md) define how to test it.

| Requirement | What already exists | What still needs to be built |
| :--- | :--- | :--- |
| FR6 — Staff access | Dashboard sign-in (`src/dashboard/`): accounts are created only by the `src.dashboard.accounts` command, passwords are stored as salted scrypt hashes, sessions use an HttpOnly SameSite cookie, and every API request re-checks the signed-in, active account. Signing in grants no role; only `approved_staff` accounts are marked as able to upload, and no route can change roles. | Enforce the upload permission on the upload screen and upload endpoint when uploads are added (phase B), with an access-denied message. |
| FR1 — Course uploads | Pipeline A reads course/category folders, converts PDF/PPTX/DOCX inputs, extracts text, and writes document outcomes and metadata. | Category upload controls, Submit, the approved-materials confirmation, alerts naming unsupported/failed files, and a visible document list. Unsupported extensions are currently skipped by normalization rather than reported to a user. |
| FR1 / FR2 — Automatic processing | Ingestion, index building, and auditing exist as separate commands. | Connect submission to processing, index refresh, and affected audit recalculation, with per-file and per-cell progress. Do not display old results as if they cover newly uploaded documents. |
| FR2 / FR5 — Dashboard | Phase A dashboard (FastAPI backend, React front end in `dashboard/`): the 36-row, 108-cell matrix of the routed results with CLO, Taught and Assessed side by side, course/skill/combined filters and a clear action that read saved results without running models, Insufficient Evidence and Generation Error reasons, and an evidence drawer with the verified quote, source file, page or slide and NLI entailment. | Pending/Processing states while uploads are processed (phase B). |
| FR7 — Default skills | Pipeline B generates S01–S12 definitions and source matches; the dashboard's skills page shows their identifiers, names, descriptions and IndSF source references with no setup, and marks skills without a source match. | — |
| FR2 / RAI2 — Progress and missing evidence | Backend helpers distinguish unavailable categories from processed categories; missing and processing-failed reasons already exist. A cell whose model output cannot be read is labelled Generation Error, with no citation and a manual-review reason, instead of Not Found. `src/run_withheld_level_cases.py` runs prepared missing and unprocessable cases for every level on real data. | Show Pending/Processing and missing/failed explanations in the dashboard, and test transitions as uploads are processed. Show Generation Error cells as failures needing manual review, not as completed results. |
| FR3 — CI authority | Only CI pages enter the CLO route, so a slide can no longer support CLO, and a missing CI gives Insufficient Evidence even when slides state CLOs. The audit report compares each slide outcome statement with the CI's numbered CLOs (repeats the CI, differs from the CI with both statements shown, not in the CI, or no CI) and lists slides that repeat the cited CI wording as corroboration. | The dashboard shows the corroborating slides beside a CI citation and, for CLO cells and on the courses page, each slide outcome statement compared with the CI (with the CI's file and page when they differ). Run the prepared CI-authority cases at the evaluation stage. |
| FR4 — Supported selections | The supported courses (`config/courses.json`) and the locked S01–S12 skills (`config/benchmark_skills.json`) are read from config; every pipeline step and count follows them. The dashboard backend rejects any unsupported course, skill or level, through the screen or direct requests, with a scope message, and offers no free-text query. | — |
| NFR4 — Small document updates | Extraction caches reuse unchanged documents. | Update changed evidence without rebuilding unrelated stores. `build_indexes.build()` currently re-embeds the full indexable corpus and rewrites all partitions. |
| NFR2 / RAI1 / RAI3 — Later evaluation stage | Tests, runtime/token logs, source verification, local-only model endpoints, and partial privacy controls exist. The ground-truth scorer (`src/evaluate_ground_truth.py`) and the blind citation check sheet with CFR/UCR scoring (`src/citation_check_sheet.py`) are ready for the labelled evaluation and the human citation review. | At the later evaluation stage, run the labelled ground-truth evaluation, human citation review, upload/role/scope tests, and synthetic privacy/payload checks. These are planned validation activities, not missing product features or current blockers. |

Implementation references: [ingestion](../src/pipeline_a_course_ingestion.py),
[format handling](../src/step0_normalize_formats.py),
[benchmark preparation](../src/pipeline_b_indsf_skills.py),
[index building](../src/build_indexes.py),
[audit runner](../src/run_skill_audit_pipeline.py),
[citation verification](../src/citation_span_verifier.py),
[CLO routing](../src/curriculum_scope.py), and
[scope/abstention](../src/scope_and_abstention_control.py).

The dashboard uses a FastAPI backend, which checks sign-in and the user's
role on every request so that direct backend requests cannot bypass FR6, and a
React front end. Phase A (viewing a saved run) is built; phase B adds uploads and
automatic processing, and phase C per-level incremental indexing (NFR4).

Known issue (2026-11-20): viewed through the VS Code tunnel, some dashboard requests
still fail intermittently, although the server answers every request when called on
the node itself (480 simultaneous requests, no failures). The front end retries a
failed read twice within a 15-second limit and then shows the error with a Try again
button, so a failure is never shown as a result. The backend and front end will run on the
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
