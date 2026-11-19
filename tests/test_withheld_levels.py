"""Withheld-level cases: case choice, the work copy and the judgement, without models."""
import json
import tempfile
import unittest
from pathlib import Path

from src.common import COURSES
from src.run_withheld_level_cases import default_cases, evaluate_case, natural_rows, prepare_case, summarise

LEVELS = ("CLO", "Taught", "Assessed")
FOLDERS = {"CLO": "01_CI_CLO", "Taught": "02_Lecture_Slides_Taught", "Assessed": "03_Assessments_Assessed"}
MISSING = "Required document category folder is empty or missing from the course repository."
FAILED = "Required document category could not be processed."


def cell(course, skill, level, routed="Not Found", reason=None, baseline="Not Found", quote=None):
    routed_part = {"final_classification": routed, "llm_called": reason is None}
    if reason:
        routed_part["abstention_reason"] = reason
    if quote:
        routed_part["verified_citation"] = {"verbatim_quote": quote}
    return {"course_code": course, "skill_id": skill, "level": level, "routed": routed_part,
            "baseline": {"final_classification": baseline}}


class WithheldLevelTest(unittest.TestCase):
    def test_default_cases_cover_every_available_level_and_one_unprocessable_course(self):
        availability = {c: {l: not (c == "SAIA2113" and l == "CLO") for l in LEVELS} for c in COURSES}
        cases = default_cases(availability)
        self.assertEqual(len([c for c in cases if c[2] == "missing"]), 8)
        self.assertNotIn(("SAIA2113", "CLO", "missing"), cases)
        self.assertEqual([c for c in cases if c[2] == "unprocessable"],
                         [("SAIA2143", l, "unprocessable") for l in LEVELS])

    def test_work_copy_withholds_one_level_and_leaves_the_source_alone(self):
        root = Path(tempfile.mkdtemp())
        course = root / "data" / "courses" / "SAIA2143_Data_Wrangling"
        for folder in FOLDERS.values():
            (course / folder).mkdir(parents=True)
            (course / folder / "file.pdf").write_bytes(b"%PDF fixture")
        outputs = root / "outputs"
        (outputs / "normalized_pdf").mkdir(parents=True)
        (outputs / "models").mkdir()
        (outputs / "industry_skills_benchmark.json").write_text("[]")
        for mode in ("missing", "unprocessable"):
            with self.subTest(mode):
                data, out = prepare_case(root / "data", outputs, root / "work" / mode, "SAIA2143", "Taught", mode)
                copy = data / "courses" / "SAIA2143_Data_Wrangling"
                taught = copy / "02_Lecture_Slides_Taught"
                if mode == "missing":
                    self.assertFalse(taught.exists())
                else:
                    self.assertEqual([p.name for p in taught.iterdir()], ["withheld_unreadable.pdf"])
                self.assertTrue((copy / "01_CI_CLO" / "file.pdf").exists())
                self.assertTrue((course / "02_Lecture_Slides_Taught" / "file.pdf").exists())  # Source untouched.
                self.assertTrue((out / "models").is_symlink())
                self.assertTrue((out / "normalized_pdf").is_dir() and not (out / "normalized_pdf").is_symlink())
                self.assertTrue((out / "industry_skills_benchmark.json").exists())

    def test_case_judgement(self):
        reference = {"cells": [cell("SAIA2143", s, l, quote="q") for s in ("S01", "S02") for l in LEVELS]}
        result = {"level_status": {"Taught": "folder_empty_or_missing"}, "cells": [
            cell("SAIA2143", "S01", "Taught", INSUFFICIENT := "Insufficient Evidence", MISSING),
            cell("SAIA2143", "S02", "Taught", INSUFFICIENT, FAILED),  # Wrong reason for a missing folder.
            cell("SAIA2143", "S01", "CLO", quote="q"), cell("SAIA2143", "S02", "CLO", quote="q"),
            cell("SAIA2143", "S01", "Assessed", quote="q"), cell("SAIA2143", "S02", "Assessed", quote="changed")]}
        row = evaluate_case("SAIA2143", "Taught", "missing", result, reference)
        self.assertEqual((row["routed_correct"], row["routed_mislabelled"], row["baseline_mislabelled"]), (1, 0, 2))
        self.assertTrue(row["level_status_correct"])
        self.assertEqual((row["other_cells"], row["other_cells_changed"]), (4, 1))

    def test_a_model_call_on_a_withheld_level_is_not_correct(self):
        result = {"level_status": {"CLO": "processing_failed"},
                  "cells": [{**cell("SAIA2143", "S01", "CLO", "Insufficient Evidence", FAILED)}]}
        result["cells"][0]["routed"]["llm_called"] = True
        self.assertEqual(evaluate_case("SAIA2143", "CLO", "unprocessable", result, None)["routed_correct"], 0)

    def test_natural_missing_levels_join_the_totals(self):
        reference = {"availability": {"SAIA2113": {"CLO": False, "Taught": True, "Assessed": True}},
                     "cells": [cell("SAIA2113", s, "CLO", "Insufficient Evidence", MISSING) for s in ("S01", "S02")]
                     + [cell("SAIA2113", "S01", "Taught")]}
        rows = natural_rows(reference)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["routed_correct"], rows[0]["baseline_mislabelled"]), (2, 2))
        totals = summarise(rows, {"commit": "x"}, "test")["totals"]
        self.assertEqual((totals["routed_mcr"], totals["baseline_mcr"]), (0.0, 1.0))
        json.dumps(totals)


if __name__ == "__main__":
    unittest.main()
