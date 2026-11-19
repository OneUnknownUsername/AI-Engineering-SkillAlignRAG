"""Courses and skills come from config/; an optional extension set adds to the locked core."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.common import COURSES, ROOT, load_courses, load_skill_definitions, read_json
from src.config import AuditConfig
from src.pipeline_b_indsf_skills import validate_skills
from src.run_skill_audit_pipeline import run
from src.skill_hypotheses import domain_terms

CORE = read_json(ROOT / "config" / "benchmark_skills.json")
EXTENSION_SKILL = {"skill_id": "S13", "skill_name": "Prompt engineering", "bucket": "E: Generative AI",
                   "sfia_codes": ["DATS"], "retrieval_query": "Design and test prompts for large language models.",
                   "nli_hypothesis_template": "The course material teaches prompt design for language models.",
                   "atomic_hypotheses": ["The course material covers prompt design.", "The course material covers testing prompts."],
                   "core_domain_terms": "prompt prompts prompting llm language model"}


def config_dir(courses=None, course_extension=None, skill_extension=None) -> Path:
    folder = Path(tempfile.mkdtemp())
    (folder / "courses.json").write_text(json.dumps(courses or {"SAIA1013": "Responsible AI and Ethics"}))
    (folder / "benchmark_skills.json").write_text(json.dumps(CORE))
    if course_extension is not None:
        (folder / "courses_extension.json").write_text(json.dumps(course_extension))
    if skill_extension is not None:
        (folder / "benchmark_skills_extension.json").write_text(json.dumps(skill_extension))
    return folder


class AuditScopeTest(unittest.TestCase):
    def test_main_has_exactly_the_three_courses_and_twelve_skills(self):
        self.assertEqual(list(COURSES), ["SAIA1013", "SAIA2113", "SAIA2143"])
        self.assertEqual([s["skill_id"] for s in load_skill_definitions()], [f"S{i:02d}" for i in range(1, 13)])
        self.assertFalse((ROOT / "config" / "courses_extension.json").exists())
        self.assertFalse((ROOT / "config" / "benchmark_skills_extension.json").exists())

    def test_extension_files_add_courses_and_skills_after_the_core(self):
        folder = config_dir(course_extension={"SAIA3013": "Deep Learning"}, skill_extension=[EXTENSION_SKILL])
        self.assertEqual(list(load_courses(folder)), ["SAIA1013", "SAIA3013"])
        skills = load_skill_definitions(folder)
        self.assertEqual([s["skill_id"] for s in skills][-2:], ["S12", "S13"])
        validate_skills(skills)

    def test_extension_cannot_repeat_a_core_course(self):
        with self.assertRaisesRegex(ValueError, "repeats core courses"):
            load_courses(config_dir(course_extension={"SAIA1013": "Another title"}))

    def test_core_skills_stay_locked(self):
        for broken in (CORE[1:], CORE + [CORE[0]]):
            with self.subTest(len(broken)), self.assertRaisesRegex(ValueError, "exactly S01-S12"):
                validate_skills(copy.deepcopy(broken))

    def test_extension_skills_need_their_own_number_and_keywords(self):
        cases = {"numbered S13 onwards": {**EXTENSION_SKILL, "skill_id": "X13"},
                 "core_domain_terms": {k: v for k, v in EXTENSION_SKILL.items() if k != "core_domain_terms"},
                 "atomic hypotheses": {k: v for k, v in EXTENSION_SKILL.items() if k != "atomic_hypotheses"}}
        for message, skill in cases.items():
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                validate_skills(copy.deepcopy(CORE) + [skill])

    def test_verifier_keywords_come_from_the_skill_for_extensions(self):
        self.assertIn("prompt", domain_terms(EXTENSION_SKILL))
        self.assertIn("cleaning", domain_terms({"skill_id": "S01"}))  # Core skills keep the built-in list.

    def test_audit_refuses_compiled_skills_that_differ_from_config(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, value in [("course_catalog_manifest.json", {"courses": {}}), ("industry_skills_benchmark.json", CORE[:11]),
                                ("parsed_course_chunks.json", []), ("verbatim_lookup_store.json", {})]:
                (output / name).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "rerun Pipeline B"):
                run(output, AuditConfig())


if __name__ == "__main__":
    unittest.main()
