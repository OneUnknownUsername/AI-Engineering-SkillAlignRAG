"""Dashboard backend: accounts, sign-in on every request (FR6), scope checks (FR4) and the views."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.common import COURSES
from src.dashboard import app as app_module
from src.dashboard.accounts import STAFF_ROLE, AccountStore, check_password, hash_password
from src.dashboard.app import COOKIE, create_app
from src.dashboard.data import NOT_FOUND_NOTE, AuditView

LEVELS = ("CLO", "Taught", "Assessed")
SKILLS = [{"skill_id": s, "skill_name": f"Skill {s}", "retrieval_query": f"Do {s}.", "bucket": "A", "sfia_codes": ["DATS"],
           "mapping_status": "mapped", "indsf_provenance": [{"doc_id": "IndSF.pdf", "role_title": "Data Scientist",
                                                              "pdf_page_no": 5, "matched_source_excerpt": "Clean data."}]}
          for s in ("S01", "S02")]


def routed(course, skill, level):
    if course == "SAIA2113" and level == "CLO":
        return {"final_classification": "Insufficient Evidence", "llm_called": False,
                "abstention_reason": "Required document category folder is empty or missing from the course repository."}
    if (course, skill, level) == ("SAIA2143", "S01", "Taught"):
        return {"final_classification": "Supported", "verified_citation": {"doc_id": "deck.pdf", "pdf_page_no": 7,
                "verbatim_quote": "Students handle missing values."}, "nli_acceptance_rule": "entailment_0.40",
                "nli_scores": {"entailment": 0.93, "hypothesis": "The course material covers data cleaning."},
                "clo_corroboration": [{"doc_id": "deck.pdf", "pdf_page_no": 2, "slide_quote": "Clean the data first."}]}
    if (course, skill, level) == ("SAIA2143", "S02", "Assessed"):
        return {"final_classification": "Generation Error", "failure_reason": "The model output could not be read; manual review required."}
    return {"final_classification": "Not Found"}


def results():
    return {"skills": SKILLS, "code_version": {"commit": "b" * 40, "uncommitted_code_changes": False},
            "hardware": {"device": "TEST"}, "availability": {c: {l: not (c == "SAIA2113" and l == "CLO") for l in LEVELS} for c in COURSES},
            "clo_slide_comparison": {c: {"ci_available": c != "SAIA2113", "ci_statements": [], "slide_pages": []} for c in COURSES},
            "cells": [{"course_code": c, "skill_id": s["skill_id"], "level": l, "routed": routed(c, s["skill_id"], l)}
                      for c in COURSES for s in SKILLS for l in LEVELS]}


class AccountTest(unittest.TestCase):
    def setUp(self):
        self.store = AccountStore(Path(tempfile.mkdtemp()) / "accounts.json")

    def test_passwords_are_hashed_and_checked(self):
        stored = hash_password("correct horse")
        self.assertTrue(check_password("correct horse", stored))
        self.assertFalse(check_password("wrong horse", stored))
        self.store.add("lecturer1", "correct horse", [STAFF_ROLE])
        text = self.store.path.read_text()
        self.assertNotIn("correct horse", text)
        self.assertEqual(oct(os.stat(self.store.path).st_mode & 0o777), "0o600")

    def test_account_rules(self):
        self.store.add("viewer1", "long enough", [])
        for args, message in [(("viewer1", "long enough", []), "already exists"), (("x", "long enough", []), "Usernames"),
                              (("viewer2", "short", []), "at least"), (("viewer3", "long enough", ["Approved Staff"]), "Invalid role")]:
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                self.store.add(*args)
        self.assertEqual(self.store.authenticate("viewer1", "long enough"), {"username": "viewer1", "roles": []})
        self.assertIsNone(self.store.authenticate("viewer1", "wrong password"))
        self.assertIsNone(self.store.authenticate("nobody", "long enough"))
        self.store.set_active("viewer1", False)
        self.assertIsNone(self.store.authenticate("viewer1", "long enough"))


class DashboardApiTest(unittest.TestCase):
    def setUp(self):
        app_module.FAILED_SIGN_IN_DELAY = 0
        tmp = Path(tempfile.mkdtemp())
        (tmp / "results.json").write_text(json.dumps(results()))
        (tmp / "lookup.json").write_text(json.dumps({
            "SAIA2143::deck.pdf::7": "Week 3 lab.\nIn this lab, STUDENTS  handle\nmissing values. Then they plot.",
            "SAIA2143::deck.pdf::2": "Outcomes: clean the data first.",
            "SAIA2143::deck.pdf::10": "Summary.", "SAIA2143::other.pdf::1": "Another document."}))
        (tmp / "catalog.json").write_text(json.dumps({"courses": {"SAIA2143": {"documents": [
            {"doc_id": "deck.pdf", "source_relative_path": "SAIA2143_X/02_Lecture_Slides_Taught/deck.pptx"}]}}}))
        self.accounts = AccountStore(tmp / "accounts.json")
        self.accounts.add("staff1", "staff password", [STAFF_ROLE])
        self.accounts.add("viewer1", "viewer password", [])
        self.client = TestClient(create_app(AuditView(tmp / "results.json", tmp / "catalog.json", tmp / "lookup.json"), self.accounts))

    def sign_in(self, username="viewer1", password="viewer password"):
        return self.client.post("/api/sign-in", json={"username": username, "password": password})

    def test_every_api_route_needs_sign_in(self):
        for path in ("/api/me", "/api/run", "/api/courses", "/api/skills", "/api/overview",
                     "/api/cells/SAIA2143/S01/Taught", "/api/anything-else"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 401)
        self.client.cookies.set(COOKIE, "made-up-token")
        self.assertEqual(self.client.get("/api/overview").status_code, 401)

    def test_sign_in_sets_a_protected_cookie_and_grants_no_role_by_itself(self):
        self.assertEqual(self.sign_in(password="wrong password").status_code, 401)
        response = self.sign_in()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_upload"])
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertTrue(self.sign_in("staff1", "staff password").json()["can_upload"])

    def test_disabling_an_account_ends_its_session_and_sign_out_works(self):
        self.sign_in()
        self.assertEqual(self.client.get("/api/me").status_code, 200)
        self.accounts.set_active("viewer1", False)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.accounts.set_active("viewer1", True)
        self.sign_in()
        self.client.post("/api/sign-out")
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_no_route_can_change_accounts_or_roles(self):
        self.sign_in()
        for method, path in (("post", "/api/accounts"), ("post", "/api/roles"), ("patch", "/api/me")):
            with self.subTest(path):
                self.assertIn(getattr(self.client, method)(path, json={"roles": [STAFF_ROLE]}).status_code, (404, 405))
        self.assertFalse(self.client.get("/api/me").json()["can_upload"])

    def test_extensions_add_routes_that_still_need_sign_in(self):
        from fastapi import Depends
        def extension(app, current_user):
            @app.get("/api/extra")
            def extra(user: dict = Depends(current_user)):
                return {"hello": user["username"]}
        tmp = Path(tempfile.mkdtemp())
        (tmp / "results.json").write_text(json.dumps(results()))
        client = TestClient(create_app(AuditView(tmp / "results.json"), self.accounts, extensions=[extension]))
        self.assertEqual(client.get("/api/extra").status_code, 401)
        client.post("/api/sign-in", json={"username": "viewer1", "password": "viewer password"})
        self.assertEqual(client.get("/api/extra").json(), {"hello": "viewer1"})

    def test_health_needs_no_sign_in_and_reveals_nothing(self):
        self.assertEqual(self.client.get("/api/health").json(), {"app": "skillalignrag-dashboard"})

    def test_two_dashboards_on_different_ports_do_not_share_sessions(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "results.json").write_text(json.dumps(results()))
        other = TestClient(create_app(AuditView(tmp / "results.json"), self.accounts, cookie_name=f"{COOKIE}_8051"))
        other.post("/api/sign-in", json={"username": "viewer1", "password": "viewer password"})
        self.assertIn(f"{COOKIE}_8051", other.cookies)
        self.assertEqual(other.get("/api/me").status_code, 200)
        # The other server's cookie means nothing here.
        self.client.cookies.set(f"{COOKIE}_8051", other.cookies[f"{COOKIE}_8051"])
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_larger_responses_are_compressed(self):
        self.sign_in()
        response = self.client.get("/api/skills", headers={"Accept-Encoding": "gzip"})
        small = self.client.get("/api/me", headers={"Accept-Encoding": "gzip"})
        self.assertNotIn("gzip", small.headers.get("content-encoding", ""))
        self.assertEqual(response.status_code, 200)

    def test_overview_and_filters(self):
        self.sign_in()
        rows = self.client.get("/api/overview").json()
        self.assertEqual(len(rows), len(COURSES) * len(SKILLS))
        self.assertEqual(len(self.client.get("/api/overview", params={"course": "SAIA2143"}).json()), 2)
        one = self.client.get("/api/overview", params={"course": "SAIA2113", "skill": "S02"}).json()
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0]["levels"]["CLO"]["status"], "Insufficient Evidence")
        self.assertIn("missing", one[0]["levels"]["CLO"]["reason"])

    def test_unsupported_selections_are_refused_with_a_scope_message(self):
        self.sign_in()
        for params in ({"course": "SAIA9999"}, {"skill": "S13"}, {"course": "SAIA2143", "skill": "S99"},
                       {"course": "saia2143"}, {"skill": "../S01"}):
            with self.subTest(params):
                response = self.client.get("/api/overview", params=params)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["out_of_scope"])
                self.assertIn("Only the supported courses", response.json()["detail"])
        for path in ("/api/cells/SAIA9999/S01/CLO", "/api/cells/SAIA2143/S13/CLO", "/api/cells/SAIA2143/S01/Rubric"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 400)

    def test_evidence_drawer_details(self):
        self.sign_in()
        supported = self.client.get("/api/cells/SAIA2143/S01/Taught").json()
        self.assertEqual(supported["citation"], {"quote": "Students handle missing values.", "doc_id": "deck.pdf",
                                                 "source_file": "SAIA2143_X/02_Lecture_Slides_Taught/deck.pptx", "page_or_slide": 7})
        self.assertEqual(supported["nli"]["entailment"], 0.93)
        not_found = self.client.get("/api/cells/SAIA1013/S01/Taught").json()
        self.assertEqual((not_found["citation"], not_found["note"]), (None, NOT_FOUND_NOTE))
        failed = self.client.get("/api/cells/SAIA2143/S02/Assessed").json()
        self.assertEqual(failed["status"], "Generation Error")
        self.assertIn("Manual review", failed["reason"])
        clo = self.client.get("/api/cells/SAIA2113/S01/CLO").json()
        self.assertFalse(clo["ci_comparison"]["ci_available"])

    def test_cited_page_text_with_the_quote_located(self):
        self.assertEqual(self.client.get("/api/cells/SAIA2143/S01/Taught/source").status_code, 401)
        self.sign_in()
        source = self.client.get("/api/cells/SAIA2143/S01/Taught/source").json()
        start, end = source["highlight"]
        # Matched despite different capitals, a double space and a line break, as the verifier matches.
        self.assertEqual(source["text"][start:end], "STUDENTS  handle\nmissing values.")
        self.assertEqual((source["source_file"], source["page_or_slide"]), ("SAIA2143_X/02_Lecture_Slides_Taught/deck.pptx", 7))
        slide = self.client.get("/api/cells/SAIA2143/S01/Taught/source", params={"item": "corroboration-0"}).json()
        self.assertEqual(slide["text"][slide["highlight"][0]:slide["highlight"][1]], "clean the data first.")

    def test_whole_cited_document_page_by_page(self):
        self.assertEqual(self.client.get("/api/cells/SAIA2143/S01/Taught/document").status_code, 401)
        self.sign_in()
        response = self.client.get("/api/cells/SAIA2143/S01/Taught/document")
        self.assertEqual(response.headers["cache-control"], "no-store")
        document = response.json()
        # Every page of the cited document in page order (10 after 7, not before it), and no other document.
        self.assertEqual([p["page"] for p in document["pages"]], [2, 7, 10])
        self.assertEqual(document["page_or_slide"], 7)
        cited = next(p["text"] for p in document["pages"] if p["page"] == 7)
        start, end = document["highlight"]
        self.assertEqual(cited[start:end], "STUDENTS  handle\nmissing values.")
        self.assertTrue(all(page["blocks"] for page in document["pages"]))  # Laid out, even without line-broken text.
        slide = self.client.get("/api/cells/SAIA2143/S01/Taught/document", params={"item": "corroboration-0"}).json()
        self.assertEqual(slide["page_or_slide"], 2)
        for path in ("/api/cells/SAIA1013/S01/Taught/document", "/api/cells/SAIA2143/S01/Taught/file"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_only_pages_a_cell_cites_are_served(self):
        self.sign_in()
        for path, params, status in [("/api/cells/SAIA1013/S01/Taught/source", {}, 404),        # Not Found cell
                                     ("/api/cells/SAIA2143/S01/Taught/source", {"item": "corroboration-5"}, 404),
                                     ("/api/cells/SAIA2143/S01/Taught/source", {"item": "../../etc"}, 404),
                                     ("/api/cells/SAIA9999/S01/Taught/source", {}, 400)]:
            with self.subTest(path=path, params=params):
                self.assertEqual(self.client.get(path, params=params).status_code, status)

    def test_skills_and_courses(self):
        self.sign_in()
        skills = self.client.get("/api/skills").json()
        self.assertEqual([s["skill_id"] for s in skills], ["S01", "S02"])
        self.assertEqual(skills[0]["sources"][0]["role"], "Data Scientist")
        courses = self.client.get("/api/courses").json()
        self.assertEqual([c["course_code"] for c in courses], list(COURSES))
        self.assertEqual(self.client.get("/api/run").json()["commit"], "b" * 40)


class PortCheckTest(unittest.TestCase):
    def test_a_running_dashboard_is_recognised(self):
        import threading
        import uvicorn
        from src.dashboard.__main__ import dashboard_running, port_is_free
        tmp = Path(tempfile.mkdtemp())
        (tmp / "results.json").write_text(json.dumps(results()))
        port = next(p for p in range(8790, 8890) if port_is_free(p))
        self.assertFalse(dashboard_running(port))
        server = uvicorn.Server(uvicorn.Config(create_app(AuditView(tmp / "results.json"), AccountStore(tmp / "a.json")),
                                               host="127.0.0.1", port=port, log_level="error"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            import time
            for _ in range(50):
                if server.started:
                    break
                time.sleep(0.1)
            self.assertTrue(dashboard_running(port))
        finally:
            server.should_exit = True
            thread.join(5)

    def test_a_paused_or_running_dashboard_gets_a_clear_message(self):
        from unittest.mock import patch
        from src.dashboard import __main__ as launcher
        cases = [({"pid": 42, "state": "T", "command": ".venv/bin/python -m src.dashboard"}, "kill -CONT 42; kill 42"),
                 ({"pid": 42, "state": "S", "command": ".venv/bin/python -m src.dashboard"}, "Stop it first: kill 42")]
        for holder, expected in cases:
            with self.subTest(holder["state"]), patch.object(launcher, "port_holder", return_value=holder):
                self.assertIn(expected, launcher.busy_port_message(8050))
        other = {"pid": 7, "state": "S", "command": "jupyter-lab"}
        with patch.object(launcher, "port_holder", return_value=other), patch.object(launcher, "dashboard_running", return_value=False):
            self.assertIsNone(launcher.busy_port_message(8050))

    def test_a_busy_port_is_detected(self):
        import socket
        from src.dashboard.__main__ import port_is_free
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen()
            self.assertFalse(port_is_free(holder.getsockname()[1]))

if __name__ == "__main__":
    unittest.main()
