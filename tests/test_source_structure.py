"""Readable layout of a page's extracted text, mapped onto the exact text the verifier checked."""
import unittest

from src.dashboard.structure import page_blocks


def layout(native, ocr="", title=""):
    text = " ".join("\n".join(filter(None, [native, ocr])).split())
    return text, [(b["kind"], b["ocr"], text[b["start"]:b["end"]]) for b in page_blocks(native, ocr, title, text)]


class SourceStructureTest(unittest.TestCase):
    def test_title_heading_wrapped_lines_and_bullets(self):
        native = ("Data Cleaning\nIn this topic you will:\n• Handle missing\nvalues in a dataset\n"
                  " Remove duplicates\nScaling is covered next week.")
        _, blocks = layout(native, title="Data Cleaning")
        self.assertEqual(blocks, [
            ("title", False, "Data Cleaning"),
            ("heading", False, "In this topic you will:"),
            ("bullet", False, "Handle missing values in a dataset"),  # The PDF's line wrap is joined back.
            ("bullet", False, "Remove duplicates"),                   # A Wingdings bullet from PowerPoint.
            ("paragraph", False, "Scaling is covered next week."),
        ])

    def test_new_paragraphs_start_after_sentence_ends_and_capitals(self):
        _, blocks = layout("The first point ends here.\nthe next line still starts a block\n"
                           "A capital starts\nanother, and\nThis joins after 'and'")
        self.assertEqual([b[2] for b in blocks], ["The first point ends here.", "the next line still starts a block",
                                                  "A capital starts another, and This joins after 'and'"])

    def test_numbered_items_and_a_bullet_glyph_on_its_own_line(self):
        _, blocks = layout("Steps\n1. Load the data\n2) Clean it\n•\nPlot the result")
        self.assertEqual(blocks, [("heading", False, "Steps"), ("numbered", False, "1. Load the data"),
                                  ("numbered", False, "2) Clean it"), ("bullet", False, "Plot the result")])

    def test_text_from_images_stays_separate(self):
        _, blocks = layout("Slide text here.", ocr="Chart label\nAxis title")
        self.assertEqual(blocks, [("paragraph", False, "Slide text here."), ("paragraph", True, "Chart label"),
                                  ("paragraph", True, "Axis title")])

    def test_positions_point_into_the_checked_text(self):
        native, ocr = "Title\n•   Spaced    bullet\ncontinued", "OCR words"
        text = " ".join(f"{native}\n{ocr}".split())
        for block in page_blocks(native, ocr, "Title", text):
            self.assertEqual(text[block["start"]:block["end"]], " ".join(text[block["start"]:block["end"]].split()))
        self.assertIn("Spaced bullet continued", [text[b["start"]:b["end"]] for b in page_blocks(native, ocr, "Title", text)])

    def test_a_title_that_does_not_start_the_page_is_not_used(self):
        _, blocks = layout("Body text first.", title="Somewhere else")
        self.assertEqual(blocks, [("paragraph", False, "Body text first.")])

    def test_text_that_does_not_match_is_shown_as_one_block(self):
        self.assertEqual(page_blocks("Different\ntext", "", "", "The checked text"),
                         [{"kind": "paragraph", "start": 0, "end": 16, "ocr": False}])


if __name__ == "__main__":
    unittest.main()
