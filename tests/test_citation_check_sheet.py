"""Citation check sheet: one blind row per distinct claim, scored per configuration."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.citation_check_sheet import COLUMNS, build_sheet, presence, score_sheet, write_sheet

SKILLS = [{"skill_id": "S01", "skill_name": "Data cleaning", "retrieval_query": "Clean raw data."}]


def supported(doc, page, quote):
    return {"final_classification": "Supported", "verified_citation": {"doc_id": doc, "pdf_page_no": page, "verbatim_quote": quote}}


def draft(label, doc=None, page=None, quote=None):
    return {"draft_classification": label, "doc_id": doc, "pdf_page_no": page, "verbatim_quote": quote}


def results():
    same = ("deck.pdf", 4, "Students clean missing values in the lab.")
    cells = [
        # Baseline claim kept by the verifier: B and B+V make the same claim. Routed: P drafts it, P+V expands the quote.
        {"course_code": "SAIA2143", "skill_id": "S01", "level": "Taught",
         "baseline": {"final_classification": "Supported", "draft": draft("Supported", *same)},
         "baseline_audit": supported(*same),
         "routed": {**supported("deck.pdf", 4, "Students clean missing values in the lab. They also remove duplicates."),
                    "draft": draft("Supported", *same), "nli_scores": {"entailment": 0.9}}},
        # Only the routed draft claims this; the verifier rejected it.
        {"course_code": "SAIA2143", "skill_id": "S01", "level": "CLO",
         "baseline": {"final_classification": "Not Found", "draft": draft("Not Found")},
         "baseline_audit": {"final_classification": "Not Found"},
         "routed": {"final_classification": "Not Found", "draft": draft("Supported", "ci.pdf", 1, "Made-up outcome text")}},
    ]
    return {"skills": SKILLS, "cells": cells, "code_version": {"commit": "a" * 40, "uncommitted_code_changes": False}}


class CitationCheckSheetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.results_path = self.tmp / "results.json"
        self.results_path.write_text(json.dumps(results()), encoding="utf-8")
        catalog = {"courses": {"SAIA2143": {"documents": [{"doc_id": "deck.pdf", "source_relative_path": "SAIA2143_X/02/deck.pptx"}]}}}
        self.catalog_path = self.tmp / "catalog.json"
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    def test_identical_claims_share_one_row_and_configurations_stay_hidden(self):
        rows, key = build_sheet(results(), None)
        self.assertEqual(len(rows), 3)  # B/B+V/P share one claim; P+V's expanded quote and P's rejected claim differ.
        shared = next(cid for cid, entry in key.items() if entry["configurations"] == ["B", "B+V", "P"])
        self.assertTrue(shared)
        self.assertEqual(sorted(c for entry in key.values() for c in entry["configurations"]), ["B", "B+V", "P", "P", "P+V"])
        self.assertFalse({"configuration", "configurations", "nli", "entailment", "gate_6a"} & set(COLUMNS))
        self.assertEqual([r["claim_id"] for r in rows], ["C001", "C002", "C003"])
        self.assertEqual(build_sheet(results(), None)[0], rows)  # Same order every time.

    def test_sheet_shows_the_source_file_and_never_overwrites(self):
        self.assertEqual(write_sheet(self.results_path, self.catalog_path, self.tmp / "check"), 3)
        with (self.tmp / "check" / "citation_check_sheet.csv").open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertIn("SAIA2143_X/02/deck.pptx", {r["source_file"] for r in rows})
        self.assertTrue(all(r["page_contains_quote"] == "" for r in rows))
        with self.assertRaises(FileExistsError):
            write_sheet(self.results_path, self.catalog_path, self.tmp / "check")

    def fill(self, answer):
        sheet = self.tmp / "check" / "citation_check_sheet.csv"
        with sheet.open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["page_contains_quote"], row["supports_skill_at_level"] = answer(row)
        with sheet.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return sheet

    def test_scores_per_configuration(self):
        write_sheet(self.results_path, self.catalog_path, self.tmp / "check")
        # The made-up CLO quote is not on its page; everything else is confirmed.
        sheet = self.fill(lambda r: ("no", "no") if r["level"] == "CLO" else ("Yes", "y"))
        report = score_sheet(sheet, self.tmp / "check" / "citation_check_key.json", self.results_path)
        s = report["scores"]
        self.assertEqual((s["P"]["claims"], s["P"]["confirmed"], s["P"]["quote_not_on_page"]), (2, 1, 1))
        self.assertEqual((s["P"]["cfr"], s["P"]["ucr"]), (0.5, 0.5))
        self.assertEqual((s["P+V"]["cfr"], s["B"]["cfr"], s["B+V"]["cfr"]), (1.0, 1.0, 1.0))

    def test_unanswered_rows_and_a_different_run_are_refused(self):
        write_sheet(self.results_path, self.catalog_path, self.tmp / "check")
        sheet = self.fill(lambda r: ("yes", "maybe"))
        with self.assertRaisesRegex(ValueError, "answer both"):
            score_sheet(sheet, self.tmp / "check" / "citation_check_key.json", self.results_path)
        other = self.tmp / "other.json"
        other.write_text(json.dumps({**results(), "cells": []}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from the one the sheet was made from"):
            score_sheet(sheet, self.tmp / "check" / "citation_check_key.json", other)

    def test_presence_counts_supported_cells_with_full_citations(self):
        report = presence(results())
        self.assertEqual(report["P+V"], {"supported_cells": 1, "with_quote_document_page": 1})
        self.assertEqual(report["P"], {"supported_cells": 2, "with_quote_document_page": 2})


if __name__ == "__main__":
    unittest.main()
