"""Phase B: uploads into the dashboard workspace, processing jobs and Pending/Processing states.

The pipeline stages are replaced by a stand-in, so these tests need no models or GPU."""
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.common import COURSES, read_json, write_json
from src.dashboard.accounts import STAFF_ROLE, AccountStore
from src.dashboard.app import create_app
from src.dashboard.data import AuditView
from src.dashboard.workspace import Workspace

LEVELS = {"01_CI_CLO": "CLO", "02_Lecture_Slides_Taught": "Taught", "03_Assessments_Assessed": "Assessed"}
SKILLS = [{"skill_id": s, "skill_name": f"Skill {s}", "retrieval_query": f"Do {s}."} for s in ("S01", "S02")]
QUOTE = "Students clean the data."


def fake_pipeline(fail_at=None, calls=None):
    """Stands in for Pipeline A, the index build and the re-audit, writing what each would write."""
    def run(args, log):
        if calls is not None:
            calls.append(list(args))
        module = args[0]
        if module == fail_at:
            raise RuntimeError(f"{module} failed in the test")
        out = Path(args[args.index("--output-dir") + 1])
        if module == "src.pipeline_a_course_ingestion":
            data = Path(args[args.index("--data-dir") + 1])
            catalog = {"courses": {}}
            for code in COURSES:
                folder = next((data / "courses").glob(code + "*"))
                docs = []
                for level_folder, level in LEVELS.items():
                    for f in sorted((folder / level_folder).glob("*")) if (folder / level_folder).is_dir() else []:
                        broken = "broken" in f.name
                        docs.append({"doc_id": f.name, "evidence_level": level, "original_format": f.suffix[1:],
                                     "source_relative_path": f"{folder.name}/{level_folder}/{f.name}",
                                     "status": "failed" if broken else "ready", "page_count": 3,
                                     "error": "FileDataError: cannot open broken document" if broken else None})
                catalog["courses"][code] = {"documents": docs, "level_availability":
                                            {l: any(d["evidence_level"] == l and d["status"] == "ready" for d in docs) for l in LEVELS.values()}}
            write_json(out / "course_catalog_manifest.json", catalog)
            write_json(out / "course_ingestion_events.json", [])
        elif module == "src.dashboard.reaudit":
            course, level = args[args.index("--course") + 1], args[args.index("--level") + 1]
            catalog = read_json(out / "course_catalog_manifest.json")
            cells = [{"course_code": course, "skill_id": s["skill_id"], "level": level,
                      "routed": {"final_classification": "Supported", "verified_citation":
                                 {"doc_id": "new.pdf", "pdf_page_no": 1, "verbatim_quote": QUOTE}}} for s in SKILLS]
            write_json(Path(args[args.index("--result") + 1]), {
                "cells": cells, "availability": catalog["courses"][course]["level_availability"],
                "clo_slide_comparison": {"ci_available": True, "ci_statements": [], "slide_pages": []},
                "code_version": {"commit": "c" * 40}})
    return run


def make_sources(tmp: Path) -> tuple[Path, Path, Path]:
    data, outputs = tmp / "data", tmp / "outputs"
    for code in COURSES:
        for level_folder in LEVELS:
            (data / "courses" / f"{code}_Course" / level_folder).mkdir(parents=True)
        (data / "courses" / f"{code}_Course" / "02_Lecture_Slides_Taught" / "week1.pdf").write_bytes(b"%PDF original")
    outputs.mkdir()
    write_json(outputs / "course_catalog_manifest.json", {"courses": {c: {"documents": [], "level_availability":
                                                                          {l: True for l in LEVELS.values()}} for c in COURSES}})
    write_json(outputs / "parsed_course_chunks.json", [])
    write_json(outputs / "verbatim_lookup_store.json", {})
    write_json(outputs / "industry_skills_benchmark.json", SKILLS)
    write_json(outputs / "course_ingestion_events.json", [])
    reference = tmp / "reference" / "results.json"
    reference.parent.mkdir()
    write_json(reference, {"skills": SKILLS, "availability": {c: {l: True for l in LEVELS.values()} for c in COURSES},
                           "clo_slide_comparison": {}, "code_version": {"commit": "a" * 40},
                           "cells": [{"course_code": c, "skill_id": s["skill_id"], "level": l,
                                      "routed": {"final_classification": "Not Found"}}
                                     for c in COURSES for s in SKILLS for l in LEVELS.values()]})
    return data, outputs, reference


class UploadTest(unittest.TestCase):
    def setUp(self, runner=None):
        self.tmp = Path(tempfile.mkdtemp())
        self.data, outputs, reference = make_sources(self.tmp)
        self.workspace = Workspace.create(self.tmp / "workspace", self.data, outputs, reference,
                                          runner=runner or fake_pipeline()).open()
        accounts = AccountStore(self.tmp / "accounts.json")
        accounts.add("staff1", "staff password", [STAFF_ROLE])
        accounts.add("viewer1", "viewer password", [])
        self.client = TestClient(create_app(None, accounts, workspace=self.workspace))

    def sign_in(self, username="staff1", password="staff password"):
        self.client.post("/api/sign-in", json={"username": username, "password": password})

    def upload(self, files, course="SAIA2143", level="Taught", declaration="true"):
        return self.client.post("/api/uploads", data={"course": course, "level": level, "declaration": declaration},
                                files=[("files", (name, content)) for name, content in files])

    def taught_cells(self):
        return [r["levels"]["Taught"] for r in self.client.get("/api/overview", params={"course": "SAIA2143"}).json()]

    def test_the_workspace_starts_as_a_copy_of_the_reference_run(self):
        self.assertTrue((self.workspace.data / "courses" / "SAIA2143_Course" / "02_Lecture_Slides_Taught" / "week1.pdf").exists())
        self.sign_in()
        self.assertEqual({c["status"] for r in self.client.get("/api/overview").json() for c in r["levels"].values()}, {"Not Found"})
        self.assertEqual(self.client.get("/api/run").json()["workspace"]["started_from"], "reference")

    def test_only_signed_in_approved_staff_may_upload(self):
        self.assertEqual(self.upload([("new.pdf", b"%PDF")]).status_code, 401)
        self.sign_in("viewer1", "viewer password")
        response = self.upload([("new.pdf", b"%PDF")])
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access denied", response.json()["detail"])
        self.assertEqual(self.workspace.jobs(), [])

    def test_the_declaration_scope_and_formats_are_checked(self):
        self.sign_in()
        self.assertIn("approved course materials", self.upload([("new.pdf", b"%PDF")], declaration="").json()["detail"])
        self.assertEqual(self.upload([("new.pdf", b"%PDF")], course="SAIA9999").status_code, 400)
        self.assertEqual(self.upload([("new.pdf", b"%PDF")], level="Rubric").status_code, 400)
        response = self.upload([("notes.txt", b"text"), ("slides.key", b"x")])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(all("Accepted formats: PDF, PPTX or DOCX" in f["reason"] for f in response.json()["files"]))

    def test_mixed_upload_keeps_the_good_files_and_explains_the_rest(self):
        self.sign_in()
        job = self.upload([("../../escape.pdf", b"%PDF new"), ("notes.txt", b"text"), ("empty.pptx", b"")]).json()
        outcomes = {f["name"]: f["outcome"] for f in job["files"]}
        self.assertEqual(outcomes, {"escape.pdf": "queued", "notes.txt": "rejected", "empty.pptx": "rejected"})
        self.workspace.process_next()
        saved = self.workspace.data / "courses" / "SAIA2143_Course" / "02_Lecture_Slides_Taught" / "escape.pdf"
        self.assertTrue(saved.exists())  # The path in the name is dropped; the file stays in its folder.
        self.assertFalse((self.data / "courses" / "SAIA2143_Course" / "02_Lecture_Slides_Taught" / "escape.pdf").exists())

    def test_cells_are_pending_then_updated_and_data_courses_is_untouched(self):
        self.sign_in()
        job = self.upload([("new.pdf", b"%PDF new"), ("broken.pdf", b"%PDF bad")]).json()
        self.assertEqual({c["state"] for c in self.taught_cells()}, {"pending"})
        self.assertEqual({c["status"] for c in self.taught_cells()}, {None})  # The old result is hidden.
        detail = self.client.get("/api/cells/SAIA2143/S01/Taught").json()
        self.assertEqual((detail["state"], detail["citation"]), ("pending", None))
        self.assertEqual(self.client.get("/api/cells/SAIA2143/S01/Taught/source").status_code, 404)
        clo = self.client.get("/api/overview", params={"course": "SAIA2143"}).json()[0]["levels"]["CLO"]
        self.assertEqual(clo["state"], "complete")  # Other levels stay current.

        self.workspace.process_next()
        finished = self.client.get("/api/uploads").json()[0]
        self.assertEqual((finished["id"], finished["state"]), (job["id"], "completed"))
        self.assertEqual({f["name"]: f["outcome"] for f in finished["files"]}, {"new.pdf": "processed", "broken.pdf": "failed"})
        self.assertIn("FileDataError", next(f for f in finished["files"] if f["name"] == "broken.pdf")["reason"])
        self.assertEqual({(c["state"], c["status"]) for c in self.taught_cells()}, {("complete", "Supported")})
        self.assertEqual(self.client.get("/api/cells/SAIA2143/S01/Taught").json()["updated_by"], job["id"])
        self.assertEqual(self.client.get("/api/run").json()["workspace"]["uploads_processed"], 1)
        documents = {(d["doc_id"], d["status"]) for d in self.client.get("/api/documents").json() if d["course_code"] == "SAIA2143"}
        self.assertIn(("new.pdf", "ready"), documents)
        self.assertEqual(sorted(p.name for p in (self.data / "courses" / "SAIA2143_Course" / "02_Lecture_Slides_Taught").iterdir()),
                         ["week1.pdf"])

    def test_a_failed_job_shows_update_failed_until_a_later_upload_succeeds(self):
        self.workspace.runner = fake_pipeline(fail_at="src.dashboard.reaudit")
        self.sign_in()
        self.upload([("new.pdf", b"%PDF new")])
        self.workspace.process_next()
        job = self.client.get("/api/uploads").json()[0]
        self.assertEqual(job["state"], "failed")
        self.assertIn("failed in the test", job["error"])
        cells = self.taught_cells()
        self.assertEqual({c["state"] for c in cells}, {"failed"})
        self.assertIn("not current", cells[0]["reason"])
        self.workspace.runner = fake_pipeline()
        self.upload([("new.pdf", b"%PDF newer")])
        self.workspace.process_next()
        self.assertEqual({c["state"] for c in self.taught_cells()}, {"complete"})

    def test_only_the_uploaded_course_is_read_again(self):
        calls = []
        self.workspace.runner = fake_pipeline(calls=calls)
        self.sign_in()
        self.upload([("new.pdf", b"%PDF new")])
        self.workspace.process_next()
        reading = next(c for c in calls if c[0] == "src.pipeline_a_course_ingestion")
        self.assertEqual(reading[-2:], ["--course", "SAIA2143"])
        # A workspace made before single-course reading has no ingestion events, so it is read in full once.
        (self.workspace.outputs / "course_ingestion_events.json").unlink()
        calls.clear()
        self.upload([("newer.pdf", b"%PDF newer")])
        self.workspace.process_next()
        reading = next(c for c in calls if c[0] == "src.pipeline_a_course_ingestion")
        self.assertNotIn("--course", reading)
        self.assertEqual(self.workspace.jobs()[0]["state"], "completed")

    def test_jobs_left_unfinished_by_a_stopped_dashboard_are_marked_failed(self):
        self.sign_in()
        self.upload([("new.pdf", b"%PDF new")])
        reopened = Workspace(self.workspace.path, runner=fake_pipeline()).open()
        job = reopened.jobs()[0]
        self.assertEqual(job["state"], "failed")
        self.assertIn("Submit the files again", job["error"])

    def test_uploads_are_not_available_when_a_saved_run_is_shown_read_only(self):
        tmp = Path(tempfile.mkdtemp())
        _, _, reference = make_sources(tmp)
        accounts = AccountStore(tmp / "accounts.json")
        accounts.add("staff1", "staff password", [STAFF_ROLE])
        client = TestClient(create_app(AuditView(reference), accounts))
        client.post("/api/sign-in", json={"username": "staff1", "password": "staff password"})
        self.assertEqual(client.get("/api/uploads").status_code, 404)
        self.assertIsNone(client.get("/api/run").json()["workspace"])


if __name__ == "__main__":
    unittest.main()
