# V1 implementation status

This is a documentation review of the checked-in source, not a claim that planned
acceptance tests have passed. [Requirements](week2_requirements.md) define the
target; [evaluation criteria](week2_evaluation_criteria.md) define how to test it.

| Requirement | What already exists | What still needs to be built |
| :--- | :--- | :--- |
| FR6 — Staff access | Dashboard sign-in (`src/dashboard/`): accounts are created only by the `src.dashboard.accounts` command, passwords are stored as salted scrypt hashes, sessions use an HttpOnly SameSite cookie, and every API request re-checks the signed-in, active account. Signing in grants no role and no route can change roles. Uploads are refused with an access-denied message, on the upload page and on the upload endpoint, for any account without the `approved_staff` role. | Run the planned role tests (student, unapproved and self-assigned accounts) at the evaluation stage. |
| FR1 — Course uploads | The dashboard's upload window (phase B, opened by the Upload button on the coverage overview) takes a course, a category (Course Information, lecture slides, assessments and rubrics) and PDF/PPTX/DOCX files, requires the approved-materials declaration, rejects unsupported, empty, oversized or duplicate files individually with the reason and the accepted formats, and reports each file's outcome (processed, or failed with the reason) and the Courses page lists every processed document by course and category. Uploads go into the dashboard workspace (`outputs/dashboard/workspace`), a copy of the course files and the reference run, so the evaluated data is never changed. | — |
| FR1 / FR2 — Automatic processing | Submitting starts a background job, one at a time: the files are saved, Pipeline A re-reads the workspace and the indexes are rebuilt, then, with only that course re-read and only the changed index stores rebuilt (NFR4), only the uploaded course and level are re-audited on the GPU (`src.dashboard.reaudit`) and merged into the workspace results, with the CI–slide comparison and CLO corroboration refreshed. A job takes about 55 seconds. | — |
| FR2 / FR5 — Dashboard | Phase A dashboard (FastAPI backend, React front end in `dashboard/`): the 36-row, 108-cell matrix of the routed results with CLO, Taught and Assessed side by side, course/skill/combined filters and a clear action that read saved results without running models, Insufficient Evidence and Generation Error reasons, and an evidence drawer with the verified quote, source file, page or slide and NLI entailment. | Pending/Processing states while uploads are processed (phase B). |
| FR7 — Default skills | Pipeline B generates S01–S12 definitions and source matches; the dashboard's skills page shows their identifiers, names, descriptions and IndSF source references with no setup, and marks skills without a source match. | — |
| FR2 / RAI2 — Progress and missing evidence | Backend helpers distinguish unavailable categories from processed categories; missing and processing-failed reasons already exist. A cell whose model output cannot be read is labelled Generation Error, with no citation and a manual-review reason, instead of Not Found. `src/run_withheld_level_cases.py` runs prepared missing and unprocessable cases for every level on real data. While an upload is queued or running, its cells show Pending or Processing with the previous result hidden; if it fails, they show Update failed until a later upload succeeds, and a job left unfinished by a stopped dashboard is marked failed. | Inspect Pending and Processing cells during the evaluation's upload tests. |
| FR3 — CI authority | Only CI pages enter the CLO route, so a slide can no longer support CLO, and a missing CI gives Insufficient Evidence even when slides state CLOs. The audit report compares each slide outcome statement with the CI's numbered CLOs (repeats the CI, differs from the CI with both statements shown, not in the CI, or no CI) and lists slides that repeat the cited CI wording as corroboration. | The dashboard shows the corroborating slides beside a CI citation and, for CLO cells and on the courses page, each slide outcome statement compared with the CI (with the CI's file and page when they differ). Run the prepared CI-authority cases at the evaluation stage. |
| FR4 — Supported selections | The supported courses (`config/courses.json`) and the locked S01–S12 skills (`config/benchmark_skills.json`) are read from config; every pipeline step and count follows them. The dashboard backend rejects any unsupported course, skill or level, through the screen or direct requests, with a scope message, and offers no free-text query. | — |
| NFR4 — Small document updates | The index keeps one embedding store per course and evidence level; `build_indexes` rewrites only the stores whose pages changed and computes vectors only for new page text, leaving every other store's files untouched, and records what it rebuilt (`last_build` in the index manifest). Pipeline A's `--course` re-reads only the uploaded course and keeps the others' records, with the same result as reading every course. An upload of a new 3-page deck rebuilt 1 of 9 stores and computed 3 vectors; the whole job took 55 seconds, mostly loading programs and models (reading 13 s, indexing 19 s of which about 18 s is loading the embedding model, re-auditing 23 s). | Run the planned before/after hash comparison at the evaluation stage. Keeping the models loaded between uploads would shorten jobs further; this is not required by NFR4. |
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
React front end. Phases A (viewing), B (uploads and automatic processing) and C
(incremental updates, NFR4) are built.

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
