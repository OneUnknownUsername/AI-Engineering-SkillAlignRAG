"""The dashboard's own copy of the course files and results, which uploads change (FR1, FR2).

The workspace starts as a copy of data/courses and of the reference run, so the evaluated
data is never touched. Each upload becomes a job; jobs run one at a time in the background:

  1. move the uploaded files into the workspace's course folder (same name = replaced)
  2. re-read that course's documents (Pipeline A) and rebuild only the index stores that changed
  3. re-audit only the uploaded course and level (src.dashboard.reaudit, on the GPU)
  4. merge the new cells into the workspace results

While a job is queued or running, its cells are Pending or Processing and their old results
are hidden; if it fails, they show Update failed until a later upload succeeds.
"""
from __future__ import annotations

import queue
import shutil
import threading
import uuid
from time import monotonic
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.clo_authority import corroborating_slides
from src.common import COURSES, LEVELS, ROOT, read_json, write_json
from src.dashboard.data import AuditView

LEVEL_FOLDERS = {level: folder for folder, level in LEVELS.items()}
ACCEPTED = {".pdf", ".pptx", ".docx"}
ACCEPTED_TEXT = "PDF, PPTX or DOCX"
MAX_BYTES = 100 * 1024 * 1024
COPIED_OUTPUTS = ("course_catalog_manifest.json", "parsed_course_chunks.json", "verbatim_lookup_store.json",
                  "course_ingestion_events.json", "normalization_manifest.json", "industry_skills_benchmark.json",
                  "indexes", "normalized_pdf", "extraction_cache")
LINKED_OUTPUTS = ("models", "tools")  # Read-only: the embedding model and LibreOffice.
DEFAULT_WORKSPACE = ROOT / "outputs" / "dashboard" / "workspace"
DEFAULT_REFERENCE = ROOT / "outputs" / "reference_run_2026-11-19_22659c7" / "skill_coverage_audit_results.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_stage(module_args: list[str], log: Path) -> None:
    from src.run_withheld_level_cases import run_stage as run
    run(module_args, log)


class UploadError(ValueError):
    """Nothing in the submission can be processed; `files` says why for each file."""

    def __init__(self, message: str, files: list[dict]):
        super().__init__(message)
        self.files = files


class Workspace:
    def __init__(self, path: Path = DEFAULT_WORKSPACE, runner: Callable = run_stage):
        self.path = Path(path)
        self.data, self.outputs = self.path / "data", self.path / "outputs"
        self.results_path, self.jobs_path = self.path / "results.json", self.path / "jobs.json"
        self.runner = runner
        self.lock = threading.RLock()
        self.queue: queue.Queue[str] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.view: AuditView | None = None

    # ---------- setting up ----------

    @classmethod
    def create(cls, path: Path, data_dir: Path, source_outputs: Path, reference: Path, **kwargs) -> "Workspace":
        """A fresh workspace copied from the course files, the pipeline outputs and a saved run."""
        workspace = cls(path, **kwargs)
        if workspace.path.exists():
            shutil.rmtree(workspace.path)
        shutil.copytree(data_dir / "courses", workspace.data / "courses")
        workspace.outputs.mkdir(parents=True)
        for name in COPIED_OUTPUTS:
            source = source_outputs / name
            if source.is_dir():
                shutil.copytree(source, workspace.outputs / name, symlinks=True)
            elif source.is_file():
                shutil.copy2(source, workspace.outputs / name)
        for name in LINKED_OUTPUTS:
            if (source_outputs / name).exists():
                (workspace.outputs / name).symlink_to((source_outputs / name).resolve())
        results = read_json(reference)
        results["workspace"] = {"started_from": str(reference), "created_at": now(), "uploads_processed": 0}
        write_json(workspace.results_path, results)
        write_json(workspace.jobs_path, {"jobs": []})
        return workspace

    def open(self) -> "Workspace":
        """Load the workspace; jobs left unfinished by a stopped dashboard are marked failed."""
        with self.lock:
            jobs = self._jobs()
            for job in jobs:
                if job["state"] in ("queued", "processing"):
                    job.update(state="failed", finished_at=now(),
                               error="The dashboard stopped before this upload finished. Submit the files again.")
            self._save_jobs(jobs)
            self._reload()
        return self

    def start(self) -> None:
        self.thread = threading.Thread(target=self._work, daemon=True, name="upload-jobs")
        self.thread.start()

    # ---------- jobs ----------

    def _jobs(self) -> list[dict]:
        return read_json(self.jobs_path)["jobs"] if self.jobs_path.exists() else []

    def _save_jobs(self, jobs: list[dict]) -> None:
        write_json(self.jobs_path, {"jobs": jobs})

    def _update_job(self, job_id: str, **changes) -> dict:
        with self.lock:
            jobs = self._jobs()
            job = next(j for j in jobs if j["id"] == job_id)
            job.update(changes)
            self._save_jobs(jobs)
            if "state" in changes:
                self._apply_states(jobs)
            return job

    def jobs(self, limit: int = 20) -> list[dict]:
        with self.lock:
            return list(reversed(self._jobs()))[:limit]

    def course_folder(self, course: str) -> Path:
        folders = [p for p in (self.data / "courses").glob(course + "*") if p.is_dir()]
        if len(folders) != 1:
            raise ValueError(f"Expected one workspace folder for {course}, found {len(folders)}")
        return folders[0]

    def submit(self, username: str, course: str, level: str, files: list[tuple[str, bytes]]) -> dict:
        """Check the files, keep the acceptable ones for the job and queue it. Course and level
        must already be in scope; the caller checks the role and the declaration."""
        outcomes, accepted = [], []
        for raw_name, content in files:
            name = Path((raw_name or "").replace("\\", "/")).name
            suffix = Path(name).suffix.lower()
            if not name or name.startswith("."):
                outcomes.append({"name": raw_name or "(no name)", "outcome": "rejected", "reason": "The file has no usable name."})
            elif suffix not in ACCEPTED:
                outcomes.append({"name": name, "outcome": "rejected",
                                 "reason": f"Unsupported format ({suffix or 'no extension'}). Accepted formats: {ACCEPTED_TEXT}."})
            elif not content:
                outcomes.append({"name": name, "outcome": "rejected", "reason": "The file is empty."})
            elif len(content) > MAX_BYTES:
                outcomes.append({"name": name, "outcome": "rejected", "reason": f"The file is larger than {MAX_BYTES // 2**20} MB."})
            elif name in {n for n, _ in accepted}:
                outcomes.append({"name": name, "outcome": "rejected", "reason": "The same file name appears twice in this upload."})
            else:
                accepted.append((name, content))
                outcomes.append({"name": name, "outcome": "queued", "reason": None})
        if not accepted:
            raise UploadError("None of the files can be processed.", outcomes)
        job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        incoming = self.path / "incoming" / job_id
        incoming.mkdir(parents=True)
        for name, content in accepted:
            (incoming / name).write_bytes(content)
        job = {"id": job_id, "user": username, "course": course, "level": level, "declaration": True,
               "files": outcomes, "state": "queued", "stage": "Waiting to start", "error": None,
               "created_at": now(), "finished_at": None}
        with self.lock:
            jobs = self._jobs() + [job]
            self._save_jobs(jobs)
            self._apply_states(jobs)
        self.queue.put(job_id)
        return job

    # ---------- processing ----------

    def _work(self) -> None:
        while True:
            self.process(self.queue.get())

    def process_next(self) -> None:
        """Process one queued job now (used by tests instead of the background thread)."""
        self.process(self.queue.get_nowait())

    def process(self, job_id: str) -> None:
        job = next(j for j in self._jobs() if j["id"] == job_id)
        course, level = job["course"], job["level"]
        log = self.path / "logs" / f"{job_id}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._update_job(job_id, state="processing", stage="Saving the files")
            folder = self.course_folder(course) / LEVEL_FOLDERS[level]
            folder.mkdir(parents=True, exist_ok=True)
            incoming = self.path / "incoming" / job_id
            files = job["files"]
            for entry in files:
                if entry["outcome"] == "queued":
                    entry["replaced"] = (folder / entry["name"]).exists()
                    shutil.move(str(incoming / entry["name"]), folder / entry["name"])
            shutil.rmtree(incoming, ignore_errors=True)

            timings, started = {}, monotonic()
            self._update_job(job_id, files=files, stage="Reading the documents")
            # Only this course is read again; the other courses keep their records (NFR4). A workspace
            # made before single-course reading lacks the records that needs, so it is read in full once.
            scope = ["--course", course] if (self.outputs / "course_ingestion_events.json").exists() else []
            self.runner(["src.pipeline_a_course_ingestion", "--data-dir", str(self.data), "--output-dir", str(self.outputs),
                         "--allow-partial", *scope], log)
            timings["reading"] = round(monotonic() - started, 1)
            catalog = read_json(self.outputs / "course_catalog_manifest.json")
            documents = {Path(d["source_relative_path"]).name: d for d in catalog["courses"][course]["documents"]
                         if Path(d["source_relative_path"]).parent.name == LEVEL_FOLDERS[level]}
            for entry in files:
                if entry["outcome"] != "queued":
                    continue
                document = documents.get(entry["name"])
                if document and document["status"] == "ready":
                    entry.update(outcome="processed", reason=None, pages=document.get("page_count"))
                else:
                    entry.update(outcome="failed", reason=(document or {}).get("error") or "The file could not be read.")

            self._update_job(job_id, files=files, stage="Updating the search indexes")
            started = monotonic()
            self.runner(["src.build_indexes", "--output-dir", str(self.outputs), "--offline"], log)
            timings["indexing"] = round(monotonic() - started, 1)
            manifest = self.outputs / "indexes" / "manifest.json"
            index_update = read_json(manifest).get("last_build") if manifest.exists() else None

            self._update_job(job_id, stage="Re-auditing the affected cells", timings=timings, index_update=index_update)
            started = monotonic()
            result_path = self.path / "logs" / f"{job_id}.result.json"
            self.runner(["src.dashboard.reaudit", "--output-dir", str(self.outputs), "--course", course, "--level", level,
                         "--result", str(result_path), "--offline"], log)
            timings["re_auditing"] = round(monotonic() - started, 1)
            self._merge(job_id, course, level, read_json(result_path))
            self._update_job(job_id, state="completed", stage="Done", finished_at=now(), timings=timings)
        except Exception as exc:  # Any failure is shown on the job and its cells, never hidden.
            message = str(exc) or type(exc).__name__
            if "CUDA" in message or "GPU" in message:
                message += " The re-audit needs the GPU: run the dashboard inside a GPU job."
            self._update_job(job_id, state="failed", stage="Failed", error=message, finished_at=now())

    def _merge(self, job_id: str, course: str, level: str, result: dict) -> None:
        with self.lock:
            results = read_json(self.results_path)
            updated = {(c["course_code"], c["skill_id"], c["level"]): c for c in result["cells"]}
            cells = []
            for cell in results["cells"]:
                key = (cell["course_code"], cell["skill_id"], cell["level"])
                cells.append({**updated.pop(key), "updated_by": job_id} if key in updated else cell)
            cells += [{**c, "updated_by": job_id} for c in updated.values()]
            # Slides can repeat the CI's wording, so refresh which slides corroborate this course's CLO citations.
            chunks = read_json(self.outputs / "parsed_course_chunks.json")
            lookup = read_json(self.outputs / "verbatim_lookup_store.json")
            for cell in cells:
                routed = cell["routed"]
                if cell["course_code"] == course and cell["level"] == "CLO" and routed["final_classification"] == "Supported":
                    routed["clo_corroboration"] = corroborating_slides(routed["verified_citation"]["verbatim_quote"],
                                                                       course, chunks, lookup)
            results["cells"] = cells
            results.setdefault("availability", {})[course] = result["availability"]
            results.setdefault("clo_slide_comparison", {})[course] = result["clo_slide_comparison"]
            info = results.setdefault("workspace", {})
            info.update(uploads_processed=info.get("uploads_processed", 0) + 1, last_update=now(),
                        last_update_code=result.get("code_version"))
            write_json(self.results_path, results)
            self._reload()

    # ---------- what the dashboard shows ----------

    def _reload(self) -> None:
        self.view = AuditView(self.results_path, self.outputs / "course_catalog_manifest.json",
                              self.outputs / "verbatim_lookup_store.json", self.outputs / "parsed_course_chunks.json")
        self._apply_states(self._jobs())

    def _apply_states(self, jobs: list[dict]) -> None:
        """The latest job for each course and level decides whether its cells are current."""
        states = {}
        for job in jobs:
            key = (job["course"], job["level"])
            if job["state"] == "queued":
                states[key] = {"state": "pending", "message": "Waiting to be re-audited after an upload."}
            elif job["state"] == "processing":
                states[key] = {"state": "processing", "message": f"Being re-audited after an upload: {job['stage'].lower()}."}
            elif job["state"] == "failed":
                states[key] = {"state": "failed", "message": f"The upload could not be processed, so this result is not current. {job['error']}"}
            else:
                states.pop(key, None)
        if self.view:
            self.view.set_states(states)

    def documents(self) -> list[dict]:
        catalog = read_json(self.outputs / "course_catalog_manifest.json")
        rows = []
        for course in COURSES:
            for document in catalog["courses"].get(course, {}).get("documents", []):
                rows.append({"course_code": course, "level": document["evidence_level"], "doc_id": document["doc_id"],
                             "file": document.get("source_relative_path", document["doc_id"]),
                             "format": document.get("original_format"), "status": document["status"],
                             "pages": document.get("page_count"), "error": document.get("error")})
        return rows

    def info(self) -> dict:
        workspace = read_json(self.results_path).get("workspace", {})
        return {"started_from": Path(workspace.get("started_from", "")).parent.name, "created_at": workspace.get("created_at"),
                "uploads_processed": workspace.get("uploads_processed", 0), "last_update": workspace.get("last_update")}
