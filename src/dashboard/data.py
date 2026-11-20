"""Read-only views of a saved audit run for the dashboard: the routed system's results only."""
from __future__ import annotations

from pathlib import Path

from src.citation_span_verifier import fold, normalize_with_offsets
from src.common import COURSES, GENERATION_ERROR, LEVELS, read_json
from src.dashboard.structure import page_blocks

LEVEL_ORDER = tuple(LEVELS.values())
NOT_FOUND_NOTE = ("No accepted evidence was found in the top three retrieved pages of this level. "
                  "This is not proof that the course lacks the skill.")
GENERATION_NOTE = "The model's answer could not be read, so this cell has no result. Manual review is required."


class ScopeError(ValueError):
    """A course, skill or level outside the supported audit scope (FR4)."""


class NoSource(LookupError):
    """The cell cites no such source, or its page text is not on this server."""


def quote_offsets(quote: str, text: str) -> list[int] | None:
    """[start, end) of the quote in the page text, matched as the citation verifier does:
    ignoring differences in whitespace, letter case, typographic quotes and dashes."""
    normalized, offsets = normalize_with_offsets(text)
    needle, _ = normalize_with_offsets(quote)
    start = fold(normalized).find(fold(needle)) if needle else -1
    if start < 0:
        return None
    return [offsets[start], offsets[start + len(needle) - 1] + 1]


class AuditView:
    def __init__(self, results_path: Path, catalog_path: Path | None = None, lookup_path: Path | None = None,
                 chunks_path: Path | None = None):
        self.results_path = Path(results_path)
        self.results = read_json(self.results_path)
        self.skills = {s["skill_id"]: s for s in sorted(self.results["skills"], key=lambda s: s["skill_id"])}
        self.cells = {(c["course_code"], c["skill_id"], c["level"]): c for c in self.results["cells"]}
        catalog = read_json(Path(catalog_path)) if catalog_path and Path(catalog_path).is_file() else None
        # Verbatim page text, as matched by the citation verifier; only cited documents are ever served.
        self.lookup = read_json(Path(lookup_path)) if lookup_path and Path(lookup_path).is_file() else {}
        # Line-broken native and OCR text and titles, used only to lay the page text out readably.
        chunks = read_json(Path(chunks_path)) if chunks_path and Path(chunks_path).is_file() else []
        self.layout = {f"{c['course_code']}::{c['doc_id']}::{c['pdf_page_no']}":
                       (c.get("native_text") or "", c.get("ocr_extracted_text") or "", c.get("slide_or_section_title") or "")
                       for c in chunks}
        self.states = {}  # (course, level) -> {state, message} while an upload changes that level
        self.files = {(course, d["doc_id"]): d.get("source_relative_path", d["doc_id"])
                      for course, info in (catalog or {}).get("courses", {}).items() for d in info["documents"]}

    def scope_message(self) -> str:
        return (f"Only the supported courses ({', '.join(COURSES)}) and benchmark skills "
                f"({', '.join(self.skills)}) can be audited.")

    def check(self, course: str | None = None, skill: str | None = None, level: str | None = None) -> None:
        if (course is not None and course not in COURSES) or (skill is not None and skill not in self.skills) \
                or (level is not None and level not in LEVEL_ORDER):
            raise ScopeError(self.scope_message())

    def run_info(self) -> dict:
        version = self.results.get("code_version") or {}
        return {"results_file": self.results_path.name, "run_folder": self.results_path.parent.name,
                "commit": version.get("commit"), "uncommitted_code_changes": version.get("uncommitted_code_changes"),
                "gpu": self.results.get("hardware", {}).get("device")}

    def set_states(self, states: dict) -> None:
        self.states = dict(states)

    def _summary(self, course: str, level: str, routed: dict) -> dict:
        pending = self.states.get((course, level))
        if pending:
            # The result from before the upload is not current, so it is not shown.
            return {"status": None, "state": pending["state"], "reason": pending["message"]}
        status = routed["final_classification"]
        reason = routed.get("abstention_reason") or (GENERATION_NOTE if status == GENERATION_ERROR else None)
        return {"status": status, "state": "complete", "reason": reason}

    def rows(self, course: str | None = None, skill: str | None = None) -> list[dict]:
        self.check(course=course, skill=skill)
        rows = []
        for code, title in COURSES.items():
            if course and code != course:
                continue
            for skill_id, definition in self.skills.items():
                if skill and skill_id != skill:
                    continue
                levels = {level: self._summary(code, level, self.cells[(code, skill_id, level)]["routed"])
                          for level in LEVEL_ORDER if (code, skill_id, level) in self.cells}
                rows.append({"course_code": code, "course_title": title, "skill_id": skill_id,
                             "skill_name": definition["skill_name"], "levels": levels})
        return rows

    def cell(self, course: str, skill: str, level: str) -> dict:
        self.check(course=course, skill=skill, level=level)
        routed = self.cells[(course, skill, level)]["routed"]
        detail = {"course_code": course, "course_title": COURSES[course], "skill_id": skill,
                  "skill_name": self.skills[skill]["skill_name"], "skill_description": self.skills[skill]["retrieval_query"],
                  "level": level, **self._summary(course, level, routed), "citation": None, "nli": None, "corroboration": [],
                  "note": None, "updated_by": self.cells[(course, skill, level)].get("updated_by")}
        if detail["state"] != "complete":
            return detail
        if detail["status"] == "Not Found":
            detail["note"] = NOT_FOUND_NOTE
        citation = routed.get("verified_citation")
        if detail["status"] == "Supported" and citation:
            detail["citation"] = {"quote": citation["verbatim_quote"], "doc_id": citation["doc_id"],
                                  "source_file": self.files.get((course, citation["doc_id"]), citation["doc_id"]),
                                  "page_or_slide": citation["pdf_page_no"]}
            scores = routed.get("nli_scores") or {}
            detail["nli"] = {"entailment": scores.get("entailment"), "hypothesis": scores.get("hypothesis"),
                             "acceptance_rule": routed.get("nli_acceptance_rule")}
            detail["corroboration"] = [{"doc_id": s["doc_id"], "page_or_slide": s["pdf_page_no"],
                                        "source_file": self.files.get((course, s["doc_id"]), s["doc_id"]),
                                        "quote": s.get("slide_quote")} for s in routed.get("clo_corroboration", [])]
        if level == "CLO":
            detail["ci_comparison"] = self.results.get("clo_slide_comparison", {}).get(course)
        return detail

    def _cited(self, course: str, skill: str, level: str, item: str) -> tuple[str, int, str]:
        """(doc_id, page, quote) of a source this cell cites: its verified citation or one corroborating slide."""
        self.check(course=course, skill=skill, level=level)
        routed = self.cells[(course, skill, level)]["routed"]
        if (course, level) in self.states:
            raise NoSource("This cell is being re-audited after an upload.")
        if routed["final_classification"] != "Supported":
            raise NoSource("This cell cites no source.")
        if item == "citation":
            cited = routed["verified_citation"]
            return cited["doc_id"], cited["pdf_page_no"], cited["verbatim_quote"]
        index = item.removeprefix("corroboration-")
        slides = routed.get("clo_corroboration", [])
        if item.startswith("corroboration-") and index.isdigit() and int(index) < len(slides):
            slide = slides[int(index)]
            return slide["doc_id"], slide["pdf_page_no"], slide.get("slide_quote") or ""
        raise NoSource("This cell cites no such source.")

    def source(self, course: str, skill: str, level: str, item: str = "citation") -> dict:
        """Text of the page this cell cites, with the quote located (for the hover preview)."""
        doc_id, page, quote = self._cited(course, skill, level, item)
        text = self.lookup.get(f"{course}::{doc_id}::{page}")
        if text is None:
            raise NoSource("The text of the cited page is not available on this server.")
        return {"doc_id": doc_id, "source_file": self.files.get((course, doc_id), doc_id), "page_or_slide": page,
                "quote": quote, "text": text, "highlight": quote_offsets(quote, text)}

    def document(self, course: str, skill: str, level: str, item: str = "citation") -> dict:
        """The whole extracted text of the document this cell cites, page by page, with the quote
        located on the cited page (for the source panel)."""
        doc_id, cited_page, quote = self._cited(course, skill, level, item)
        prefix = f"{course}::{doc_id}::"
        numbers = sorted(int(key[len(prefix):]) for key in self.lookup
                         if key.startswith(prefix) and key[len(prefix):].isdigit())
        if cited_page not in numbers:
            raise NoSource("The text of the cited document is not available on this server.")
        pages = []
        for n in numbers:
            text = self.lookup[f"{prefix}{n}"]
            native, ocr, title = self.layout.get(f"{prefix}{n}", (text, "", ""))
            pages.append({"page": n, "text": text, "blocks": page_blocks(native, ocr, title, text)})
        cited_text = self.lookup[f"{prefix}{cited_page}"]
        return {"doc_id": doc_id, "source_file": self.files.get((course, doc_id), doc_id), "page_or_slide": cited_page,
                "quote": quote, "pages": pages, "highlight": quote_offsets(quote, cited_text)}

    def courses(self) -> list[dict]:
        availability = self.results.get("availability", {})
        return [{"course_code": code, "course_title": title, "availability": availability.get(code, {}),
                 "ci_comparison": self.results.get("clo_slide_comparison", {}).get(code)} for code, title in COURSES.items()]

    def skill_list(self) -> list[dict]:
        return [{"skill_id": s["skill_id"], "skill_name": s["skill_name"], "description": s["retrieval_query"],
                 "bucket": s.get("bucket"), "sfia_codes": s.get("sfia_codes", []), "mapping_status": s.get("mapping_status"),
                 "sources": [{"document": p["doc_id"], "role": p.get("role_title"), "page": p.get("pdf_page_no"),
                              "excerpt": p.get("matched_source_excerpt")} for p in s.get("indsf_provenance", [])]}
                for s in self.skills.values()]
