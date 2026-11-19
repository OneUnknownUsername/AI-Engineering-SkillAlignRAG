"""Scorer tests with made-up runs and labels; no model or course data needed."""
import csv
import tempfile
import unittest
from pathlib import Path

from src.common import COURSES
from src.evaluate_ground_truth import read_ground_truth, run_score, score, write_template

LEVELS = ("CLO", "Taught", "Assessed")
AVAILABILITY = {"SAIA1013": {"CLO": True, "Taught": True, "Assessed": True},
                "SAIA2113": {"CLO": False, "Taught": True, "Assessed": True}}


def cell(course, skill, level, routed="Not Found", draft=None, baseline="Not Found", audit=None,
         routed_failed=False, baseline_failed=False):
    if not AVAILABILITY[course][level]:
        routed_part = {"final_classification": "Insufficient Evidence", "abstention_reason": "missing", "llm_called": False}
    else:
        routed_part = {"final_classification": routed, "draft": {"draft_classification": draft or routed}}
    if routed_failed:
        routed_part["generation_error"] = "bad JSON"
    baseline_part = {"final_classification": baseline, "draft": {"draft_classification": baseline}}
    if baseline_failed:
        baseline_part["generation_error"] = "bad JSON"
    return {"course_code": course, "skill_id": skill, "level": level, "routed": routed_part,
            "baseline": baseline_part, "baseline_audit": {"final_classification": audit or baseline}}


def results(overrides=None):
    overrides = overrides or {}
    cells = [cell(c, s, l, **overrides.get((c, s, l), {})) for c in AVAILABILITY for s in ("S01", "S02") for l in LEVELS]
    return {"availability": AVAILABILITY, "cells": cells, "hardware": {"device": "test"}, "benchmark_fingerprint": "f"}


def truth_rows(labels=None):
    labels = labels or {}
    rows = []
    for c in AVAILABILITY:
        for s in ("S01", "S02"):
            for l in LEVELS:
                default = "Not Found" if AVAILABILITY[c][l] else "Insufficient Evidence"
                rows.append({"course_code": c, "skill_id": s, "skill_name": "x", "level": l,
                             "label": labels.get((c, s, l), default), "evidence_pages": "doc p1",
                             "note": "", "lecturer_checked": "no"})
    return rows


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


class ScorerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def scores(self, run, rows):
        truth, _ = read_ground_truth(write_csv(self.tmp / "gt.csv", rows), run)
        return score(run, truth)

    def test_perfect_routed_answers_score_one(self):
        key = ("SAIA1013", "S01", "Taught")
        s = self.scores(results({key: {"routed": "Supported"}}), truth_rows({key: "Supported"}))
        self.assertEqual(s["P+V"]["levels"]["Taught"]["f1"], 1.0)
        self.assertEqual(s["B"]["levels"]["Taught"]["fn"], 1)

    def test_supported_claim_on_missing_document_is_a_false_alarm(self):
        # Decision 2: ground-truth Insufficient Evidence cells stay in as "no".
        key = ("SAIA2113", "S01", "CLO")
        s = self.scores(results({key: {"baseline": "Supported"}}), truth_rows())
        self.assertEqual(s["B"]["levels"]["CLO"]["fp"], 1)
        self.assertEqual(s["B"]["missing_document_mislabelled"], 2)  # Baseline never abstains.
        self.assertEqual(s["P+V"]["missing_document_mislabelled"], 0)
        self.assertEqual(s["P+V"]["missing_document_conflation_rate"], 0.0)

    def test_failed_output_counts_as_no_and_is_counted(self):
        # Decision 3: a failure on a Supported cell is a miss, whatever label was stored.
        key = ("SAIA1013", "S02", "Assessed")
        s = self.scores(results({key: {"routed": "Supported", "routed_failed": True}}), truth_rows({key: "Supported"}))
        level = s["P+V"]["levels"]["Assessed"]
        self.assertEqual((level["tp"], level["fn"], level["failed"]), (0, 1, 1))
        self.assertEqual(s["P+V"]["confusion"]["Assessed"]["Supported"]["Failed output"], 1)
        self.assertEqual(s["P+V"]["failed_outputs"], 1)

    def test_level_without_supported_cells_has_no_f1_and_is_left_out(self):
        key = ("SAIA1013", "S01", "Taught")
        s = self.scores(results({key: {"routed": "Supported"}}), truth_rows({key: "Supported"}))
        self.assertIsNone(s["P+V"]["levels"]["CLO"]["f1"])
        self.assertEqual(s["P+V"]["levels_without_f1"], ["CLO", "Assessed"])
        self.assertEqual(s["P+V"]["macro_f1"], 1.0)

    def test_p_uses_the_draft_before_the_verifier(self):
        key = ("SAIA1013", "S01", "Taught")
        s = self.scores(results({key: {"routed": "Not Found", "draft": "Supported"}}), truth_rows({key: "Supported"}))
        self.assertEqual(s["P"]["levels"]["Taught"]["tp"], 1)
        self.assertEqual(s["P+V"]["levels"]["Taught"]["fn"], 1)

    def test_gain_over_baseline(self):
        key = ("SAIA1013", "S01", "Taught")
        s = self.scores(results({key: {"routed": "Supported"}}), truth_rows({key: "Supported"}))
        self.assertEqual(s["P+V"]["macro_f1_gain_over_b"], 1.0)  # B has 0.0 on the same level.

    def test_bad_files_are_refused(self):
        run = results()
        rows = truth_rows()
        cases = {"no row for": rows[1:], "duplicate": rows + rows[:1],
                 "must be one of": [{**rows[0], "label": "Yes"}] + rows[1:],
                 "has documents": [{**rows[0], "label": "Insufficient Evidence"}] + rows[1:],
                 "is missing documents": [r if r["course_code"] != "SAIA2113" or r["level"] != "CLO" else {**r, "label": "Not Found"} for r in rows],
                 "not a cell": rows + [{**rows[0], "skill_id": "S99"}]}
        for message, bad in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                read_ground_truth(write_csv(self.tmp / "bad.csv", bad), run)

    def test_labels_tolerate_case_and_spacing(self):
        rows = truth_rows()
        rows[0]["label"] = "  not   found "
        truth, _ = read_ground_truth(write_csv(self.tmp / "gt.csv", rows), results())
        self.assertEqual(truth[("SAIA1013", "S01", "CLO")]["label"], "Not Found")

    def test_supported_without_pages_is_a_warning(self):
        key = ("SAIA1013", "S01", "Taught")
        rows = truth_rows({key: "Supported"})
        for r in rows:
            r["evidence_pages"] = ""
        _, warnings = read_ground_truth(write_csv(self.tmp / "gt.csv", rows), results())
        self.assertEqual(len(warnings), 1)

    def test_score_writes_both_reports(self):
        import json
        run_path = self.tmp / "results.json"
        run_path.write_text(json.dumps(results()), encoding="utf-8")
        report = run_score(run_path, write_csv(self.tmp / "gt.csv", truth_rows()), self.tmp / "out")
        self.assertTrue((self.tmp / "out" / "evaluation_scores.md").exists())
        self.assertEqual(report["inputs"]["ground_truth_rows"], 12)

    def test_template_prefills_missing_levels_and_never_overwrites(self):
        catalog = {"courses": {c: {"level_availability": {l: not (c == "SAIA2113" and l == "CLO") for l in LEVELS}}
                               for c in COURSES}}
        skills = [{"skill_id": "S02", "skill_name": "B"}, {"skill_id": "S01", "skill_name": "A"}]
        path = self.tmp / "gt" / "template.csv"
        self.assertEqual(write_template(path, catalog, skills), len(COURSES) * 2 * 3)
        with path.open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        prefilled = [r for r in rows if r["label"]]
        self.assertEqual([(r["course_code"], r["level"], r["label"]) for r in prefilled],
                         [("SAIA2113", "CLO", "Insufficient Evidence")] * 2)
        self.assertEqual(rows[0]["skill_id"], "S01")
        with self.assertRaises(FileExistsError):
            write_template(path, catalog, skills)


if __name__ == "__main__":
    unittest.main()


class CodeVersionTest(unittest.TestCase):
    def test_commit_and_uncommitted_code_edits_are_recorded(self):
        import subprocess
        from src.common import code_version
        repo = Path(tempfile.mkdtemp())
        self.assertEqual(code_version(repo)["commit"], "not recorded")
        git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
        git("init", "-q")
        (repo / "src").mkdir()
        (repo / "src" / "a.py").write_text("x = 1\n")
        git("add", ".")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        clean = code_version(repo)
        self.assertEqual((len(clean["commit"]), clean["uncommitted_code_changes"]), (40, False))
        (repo / "notes.txt").write_text("not code\n")  # Files outside src/ and config/ are ignored.
        self.assertFalse(code_version(repo)["uncommitted_code_changes"])
        (repo / "src" / "a.py").write_text("x = 2\n")
        dirty = code_version(repo)
        self.assertEqual((dirty["uncommitted_code_changes"], dirty["changed_paths"]), (True, ["src/a.py"]))

    def test_scorer_warns_about_unknown_or_edited_code(self):
        import json
        tmp = Path(tempfile.mkdtemp())
        truth = write_csv(tmp / "gt.csv", truth_rows())
        cases = {"predates": {}, "uncommitted code changes": {"code_version": {
            "commit": "a" * 40, "uncommitted_code_changes": True, "changed_paths": ["src/x.py"]}}}
        for message, extra in cases.items():
            path = tmp / f"{len(message)}.json"
            path.write_text(json.dumps({**results(), **extra}), encoding="utf-8")
            report = run_score(path, truth, tmp / "out")
            with self.subTest(message):
                self.assertIn(message, report["warnings"][0])
        self.assertIn("uncommitted changes to src/x.py", (tmp / "out" / "evaluation_scores.md").read_text(encoding="utf-8"))
