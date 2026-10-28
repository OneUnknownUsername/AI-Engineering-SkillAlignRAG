"""Stage B1: recover role-scoped records from native/OCR text and table rows.

No PDF page numbers or benchmark excerpts participate in extraction. Markdown
tables take precedence over flattened text for responsibility-level columns.
"""
from __future__ import annotations

import re
import unicodedata

from src.common import fingerprint, normalize

SECTIONS = ("job_description_tasks", "essential_skills", "competencies", "common_tools", "sfia_level_definitions")
CODE = re.compile(r"\(([A-Z]{4})\)")
LEVEL = re.compile(r"[1-7](?:\s*[,/]\s*[1-7])*")
ROLE = re.compile(
    r"(?:(?:Associate|Senior|Principal|Principle|Head|Director)\s+)?"
    r"(?:AI\s*/\s*ML\s+Engineer|AI\s+Researcher\s*-\s*(?:Theoretical|Applied)|"
    r"AI\s+(?:Ethics\s+Officer|Product\s+Manager|Application\s+Developer)|"
    r"AI\s+DevOps(?:\s*/\s*MLOps\s+Engineer)?|MLOps\s+Engineer|"
    r"Data\s+(?:Analyst|Scientist|Engineer|Architect))", re.I)
HEADINGS = {
    "JOB DESCRIPTION": "job_description_tasks", "ESSENTIAL SKILLS": "essential_skills",
    "COMPETENCIES": "competencies", "SKILLS AND COMPETENCIES": "competencies",
    "COMMON TOOLS": "common_tools", "SOFT SKILLS": None, "SOFTS SKILLS": None,
    "COMMON CERTIFICATION": None, "COMMON QUALIFICATIONS": None, "CAREER PATHWAYS": None,
    "CAREER PATHWAY": None,
}
ACTION = re.compile(
    r"^(?:Assists?|Applies|Analyses|Designs?|Develops?|Performs?|Establishes|Uses|Engages|"
    r"Defines|Follows|Provides|Reviews|Prioritises|Investigates|Deals|Carries|Evaluates?|Identifies|"
    r"Contributes?|Understands?|Selects?|Publishes|Participates|Implements?|Advises|Plans|Supports?|"
    r"Monitors?|Obtains|Negotiates|Ensures?|Helps?|Creates?|Recommends?|Coordinates|Coaches|Faces|"
    r"Represents|Collect|Utilise|Collaborate|Assist|Apply|Work|Converts|Specifies|Optimises|Take|"
    r"Responsible|Translates|Owns|Executes|Drives|Manages|Writes|Learns|Distinguishes|Acquires|"
    r"Sources|Examines|Addresses|Recruits|Partners|Strong command|Knowledge of|Experience|"
    r"Familiarity|Proven ability|To ensure|Engage|Facilitates|Communicate|Data scientist code)\b", re.I)
QUALIFICATION = re.compile(r"^(?:Professional cert|Bachelor|Diploma|Degree|Post-?graduate|Graduate,|MBA|Tools specific cert|Relevant cert|Law degree|Machine learning and AI courses)", re.I)
SOFT = re.compile(r"^(?:Problem[- ]solving|Critical and analytical|Creativity|Strong communication|Self-starting|Team\s?work|Pro-active data collaboration|Agile and fast|Collaborative skills|Intellectual curiosity|Report writing|Communication skills|Listening skills|Leadership skills|Storytelling skills|Articulate product visions|Good communication skills|Analytical mindset|Self-motivated|Ability to work|Ability to build a network|Ability to prioritize|Strong verbal|Highly motivated|Committed to|Strong project management)", re.I)
TECHNICAL_START = re.compile(r"^(?:AI/ML/Deep|Mathematical Skills|The ethical issues|Technical knowledge|Able to|Mastering|Ability to (?:design|build)|Distinguishes|Executes|Performs SWOT|Learns|Acquires|Sources data|Examines|Addresses ethics)", re.I)


def clean_ocr(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00a7", "").replace("\x00", "")
    text = text.replace("\u00ad", "").replace("\u2013", "-").replace("\u2014", "-")
    return normalize(text)


def canonical_role(text: str) -> str:
    text = clean_ocr(text).replace("Principle", "Principal").replace("principle", "Principal")
    text = re.sub(r"\s*/\s*", "/", text)
    text = text.title().replace("Ai", "AI").replace("Ml", "ML").replace("Mlops", "MLOps").replace("Devops", "DevOps")
    if text == "AI DevOps" or text == "AI DevOps/MLOps Engineer":
        return "AI DevOps / MLOps Engineer"
    return text


def seniority(role: str) -> str:
    if re.search(r"\b(?:senior|principal|principle|head|director|management)\b|product manager", role, re.I):
        return "senior_management"
    return "entry_associate" if re.search(r"associate", role, re.I) else "mid_level"


def page_role(text: str, previous: str | None) -> str | None:
    key = re.search(r"key functions of (?:a|an)\s+(data\s+(?:analyst|scientist|engineer|architect))", normalize(text), re.I)
    if key:
        return canonical_role(key[1])
    lines = [clean_ocr(line) for line in text.splitlines() if line.strip()]
    if lines and ROLE.fullmatch(lines[0]):
        return canonical_role(lines[0])
    # Continuation pages identify the role in the table introduction.
    intro = re.search(r"(?:seniority levels for|tools used by) (?:a|an)\s+(data\s+(?:analyst|scientist|engineer|architect))", normalize(text), re.I)
    return canonical_role(intro[1]) if intro else previous


def heading(line: str) -> tuple[bool, str | None]:
    label = re.sub(r"\s*\(CON['\u2019]?T\)\s*", "", clean_ocr(line), flags=re.I).rstrip(":").upper()
    return label in HEADINGS, HEADINGS.get(label)


def table_rows(markdown: str):
    for line in markdown.splitlines():
        if line.strip().startswith("|"):
            cells = [clean_ocr(c) for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            if any(cells) and not all(not c or re.fullmatch(r"[-: ]+", c) for c in cells):
                yield line, cells


def native_competency_rows(text: str, role: str):
    """Fallback for OCR tables when pdfplumber did not recover cells."""
    lines = [clean_ocr(line) for line in text.splitlines() if line.strip()]
    header_words = {"Skills", "Data", "Analyst", "Scientist", "Engineer", "Architect", "Senior", "Principle", "Principal", "Head"}
    for index, line in enumerate(lines):
        if not CODE.search(line):
            continue
        values = []
        end = index + 1
        while end < len(lines) and LEVEL.fullmatch(lines[end]):
            values.append(lines[end])
            end += 1
        if not values:
            continue
        start = index
        while start > 0 and not LEVEL.fullmatch(lines[start - 1]) and lines[start - 1] not in header_words and not heading(lines[start - 1])[0]:
            if CODE.search(lines[start - 1]):
                break
            start -= 1
        label = " ".join(lines[start:index + 1])
        titles = [role, "Senior " + role, "Principal " + role, "Head " + role]
        if len(values) == 3 and "Head" in lines[:index] and "Senior" in lines[:index]:
            titles = titles[1:]
        yield " ".join(lines[start:end]), ["Skills", *titles[:len(values)]], [label, *values]


def native_appendix_tools(text: str) -> list[str]:
    """Recover category/example pairs from OCR-only Appendix B tables."""
    result, category, examples = [], "", []
    for line in text.splitlines():
        value = clean_ocr(line)
        if re.match(r"Disclaimer", value, re.I):
            break
        if not value or re.match(r"Appendix\b|This section\b|COMMON TOOLS$|EXAMPLES$", value, re.I):
            continue
        if re.search(r"(?:Tools|Technologies|Frameworks|Libraries\s*\(Packages\))$", value, re.I):
            if value == "Tools" and category and not examples:
                category += " Tools"
                continue
            if category and examples:
                result.append(category + ": " + " ".join(examples))
            category, examples = value, []
        elif category:
            examples.append(value)
    if category and examples:
        result.append(category + ": " + " ".join(examples))
    return result


def split_items(lines: list[str], section: str) -> list[str]:
    """Join wrapped lines; task starts and explicit bullets delimit records."""
    result, current = [], []
    for line in lines:
        line = clean_ocr(line)
        if not line or re.fullmatch(r"\d{1,3}|\(CON['\u2019]?T\)|[A-Z]{7,}", line):
            continue
        bullet = re.match(r"^(?:[\u2022\u00b7\uf0b7*\-]\s+|[a-z]\)\s*|\d+[.)]\s+)", line)
        content = line[bullet.end():] if bullet else line
        new = bool(bullet) or bool(current and content[:1].isupper() and ACTION.match(content))
        if section == "essential_skills" and current:
            new = new or bool(CODE.search(" ".join(current)))
        if section == "common_tools" and current:
            prior = " ".join(current)
            # Short tool names are rows, except obvious line-wrapped continuations.
            new = new or not (prior.endswith((" and", " for", " of", " AI", "Data")) or
                                 content[:1].islower() or content in {"Platform", "Science and Public Policy"} or
                                 content.startswith("("))
        if section in {"essential_skills", "competencies"} and current and not CODE.search(" ".join(lines)):
            prior = current[-1]
            new = new or (content[:1].isupper() and not prior.endswith((",", " in", " of", " and", "AI", "system", "machine", "with", "for"))
                          and len(content.split()) > 1 and len(prior.split()) > 1)
        if new and current:
            result.append(" ".join(current))
            current = []
        current.append(content)
    if current:
        result.append(" ".join(current))
    return result


def extract_all_skills(raw: list[dict]) -> list[dict]:
    records: dict[tuple, dict] = {}

    def add(page, role, section, text, *, levels=(), source=None, source_field=None, scope="role", base_role=None):
        text = clean_ocr(text)
        if not text or (len(re.findall(r"[A-Za-z]", text)) < 2 and text not in {"R", "C"}):
            return
        codes = sorted(set(CODE.findall(text)))
        key = (page["doc_id"], role, section, text.casefold(), tuple(levels))
        if source_field is None:
            source_field = next((field for field in ("native_text", "ocr_extracted_text", "verbatim_text_span")
                                 if clean_ocr(source or text) in clean_ocr(page.get(field, ""))), "verbatim_text_span")
        occurrence = {"pdf_page_no": page["pdf_page_no"], "source_field": source_field, "source_text": source or text}
        if key in records:
            records[key]["source_occurrences"].append(occurrence)
            return
        records[key] = {"item_id": "INDSF-" + fingerprint(key)[:20], "doc_id": page["doc_id"],
                        "pdf_page_no": page["pdf_page_no"], "role_title": role,
                        "base_role_title": base_role or role, "seniority_tier": seniority(role),
                        "section_type": section, "sfia_codes": codes, "sfia_levels": list(levels),
                        "verbatim_text": text, "scope": scope, "source_occurrences": [occurrence]}

    previous, active_section, appendix = {}, {}, {}
    for page in sorted(raw, key=lambda p: (p["doc_id"], p["pdf_page_no"])):
        doc = page["doc_id"]
        native = page.get("native_text", "")
        ocr = page.get("ocr_extracted_text", "")
        native_sections = [heading(line)[1] for line in native.splitlines() if heading(line)[0]]
        if native.strip() and not any(heading(line)[0] for line in ocr.splitlines()):
            # Native-rich pages sometimes produce tiny OCR fragments from icons.
            # Keep full OCR-only pages and explicitly headed OCR sections intact.
            tools_continuation = bool(native_sections and native_sections[-1] == "common_tools")
            ocr = "\n".join(line for line in ocr.splitlines() if
                            CODE.search(line) or ACTION.match(clean_ocr(line)) or TECHNICAL_START.match(clean_ocr(line)) or
                            (tools_continuation and re.fullmatch(r"[A-Za-z][A-Za-z0-9 .,+/-]*", line.strip())
                             and not re.fullmatch(r"(.)\1{3,}", line.strip())))
        text = native + ("\n" + ocr if ocr.strip() else "") if native.strip() else ocr or page.get("verbatim_text_span", "")
        if "\n" not in text:
            # Some external OCR exports preserve only whitespace-normalized spans.
            labels = "|".join(re.escape(label) for label in sorted(HEADINGS, key=len, reverse=True))
            text = re.sub(r"\b(" + labels + r")\b", r"\n\1\n", text, flags=re.I)
            text = re.sub(r"(?<=\.)\s+(?=[A-Z])", "\n", text)
        flat = clean_ocr(text)
        if not flat:
            continue
        app = re.match(r"Appendix\s+([A-Z])\b", flat, re.I)
        if app:
            appendix[doc] = app[1].upper()
        role = page_role(text, previous.get(doc))
        if role != previous.get(doc):
            active_section[doc] = None
        previous[doc] = role
        rows = list(table_rows(page.get("tables_markdown", "")))
        if appendix.get(doc) == "A":
            found = False
            for line, cells in rows:
                if len(cells) == 2 and re.fullmatch(r"[1-7]", cells[0]):
                    add(page, "Framework-wide", "sfia_level_definitions", " ".join(cells), levels=[int(cells[0])],
                        source=line, source_field="tables_markdown", scope="framework")
                    found = True
            if not found:
                for m in re.finditer(r"(?:^|\n)\s*([1-7])\s*\n([^\n]+)", text):
                    add(page, "Framework-wide", "sfia_level_definitions", m[0], levels=[int(m[1])], scope="framework")
            continue
        if appendix.get(doc) == "B":
            for line, cells in rows:
                if len(cells) == 2 and cells[0] not in {"COMMON TOOLS", ""} and cells[1] != "EXAMPLES":
                    add(page, "Framework-wide", "common_tools", ": ".join(cells), source=line,
                        source_field="tables_markdown", scope="framework")
            if not rows:
                for item in native_appendix_tools(text):
                    add(page, "Framework-wide", "common_tools", item, scope="framework")
            continue
        if appendix.get(doc) or not role:
            continue
        if re.match(r"(?:Published by|ACKNOWLEDGEMENT|CAREER PATHWAY[S]?\s*-)", flat, re.I):
            active_section[doc] = None
            continue

        # Extract actual table cells, not pdfplumber's duplicate enclosing layout cells.
        table_competencies = False
        headers = []
        competency_source = "tables_markdown"
        skill_rows = rows
        if "SKILLS AND COMPETENCIES" in flat and not any(
            any(CODE.search(cell) and len(cell) < 140 and i + 1 < len(cells) and LEVEL.fullmatch(cells[i + 1])
                for i, cell in enumerate(cells)) for _, cells in rows
        ):
            skill_rows = []
            for source, header, cells in native_competency_rows(text, role):
                skill_rows.extend([(source, header), (source, cells)])
            competency_source = "native_text"
        for line, cells in skill_rows:
            if "Skills" in cells:
                pos = cells.index("Skills")
                headers = cells[pos + 1:]
                continue
            for i, cell in enumerate(cells):
                if not CODE.search(cell) or len(cell) > 140:
                    continue
                values = []
                for value in cells[i + 1:]:
                    if not LEVEL.fullmatch(value):
                        break
                    values.append(value)
                if not values:
                    continue
                table_competencies = True
                for column, value in enumerate(values):
                    label = headers[column] if column < len(headers) else ""
                    # The architect table in this edition mislabels its columns as
                    # engineer. Preserve that source label but scope to the active role.
                    if re.search(r"head", label, re.I):
                        title = "Head " + role
                    elif re.search(r"princip", label, re.I):
                        title = "Principal " + role
                    elif re.search(r"senior", label, re.I):
                        title = "Senior " + role
                    else:
                        title = role
                    levels = [int(n) for n in re.findall(r"[1-7]", value)]
                    add(page, title, "competencies", cell + " | " + value,
                        levels=levels, source=line, source_field=competency_source, base_role=role)

        lines = text.splitlines()
        # DS introductory prose isolates the task body from career-pathway diagrams.
        key = re.search(r"This section describes the key functions of (?:a|an)\s+data\s+\w+\s*:", text, re.I)
        if key:
            for item in split_items(text[key.end():].splitlines(), "job_description_tasks"):
                add(page, role, "job_description_tasks", item)
            active_section[doc] = None
            continue
        # Tool and competency columns can appear in either reading order. DS tools
        # are a contiguous list beginning at their explicit introductory sentence.
        tools_intro = re.search(r"This section lists the common tools used by (?:a|an)\s+data\s+\w+\s*:", text, re.I)
        if tools_intro:
            block = re.split(r"This section|\n(?:Data\s*\n(?:Engineer|Scientist)|Senior\s*\n|Skills\s*\n|Note\b|COMMON QUALIFICATIONS)", text[tools_intro.end():], maxsplit=1)[0]
            if not block.strip():
                block = "\n".join(line for line in lines if re.match(r"\s*[\u2022\u00b7\uf0b7]\s*", line))
            for item in split_items(block.splitlines(), "common_tools"):
                add(page, role, "common_tools", item)
        if table_competencies:
            active_section[doc] = None
            continue

        section = active_section.get(doc)
        buffer = []

        def flush():
            if section and buffer:
                for item in split_items(buffer, section):
                    add(page, role, section, item)
            buffer.clear()

        has_job = "JOB DESCRIPTION" in flat
        has_essential = "ESSENTIAL SKILLS" in flat
        has_tools = "COMMON TOOLS" in flat
        for index, line in enumerate(lines):
            value = clean_ocr(line)
            is_heading, next_section = heading(value)
            if is_heading:
                flush()
                # Adjacent column headings precede the actual first column body.
                next_lines = [clean_ocr(s) for s in lines[index + 1:] if clean_ocr(s)]
                adjacent = bool(next_lines and heading(next_lines[0])[0])
                if next_section is None and adjacent:
                    continue
                if value.upper() in {"SOFT SKILLS", "SOFTS SKILLS"} and section in {"job_description_tasks", "essential_skills"}:
                    continue
                section = next_section
                continue
            if ROLE.fullmatch(value) or re.fullmatch(r"\d{1,3}|\(CON['\u2019]?T\)", value, re.I):
                continue
            if re.match(r"^(?:Disclaimer|Note:|Published by|All rights reserved)", value, re.I):
                flush()
                section = None
                break
            if QUALIFICATION.match(value) or SOFT.match(value):
                flush()
                section = None
            if QUALIFICATION.match(value):
                continue
            # Recover technical columns displaced after certifications/soft skills.
            if section is None and has_job and ACTION.match(value) and not re.match(r"(?:Strong|Experience)", value):
                section = "job_description_tasks"
            if section is None and has_essential and TECHNICAL_START.match(value):
                section = "essential_skills"
            if section is None and has_essential and "COMPETENCIES" in flat and re.match(r"Experience with MLOps", value):
                section = "competencies"
            if section == "competencies" and has_essential and re.match(r"Ability to (?:design|build)", value):
                flush()
                section = "essential_skills"
            if has_essential and "COMPETENCIES" in flat and section == "essential_skills" and re.match(r"(?:Designs|Applies|Works|Converts|Performs statistical|Specifies|Experience with MLOps)", value):
                flush()
                section = "competencies"
            if has_essential and re.match(r"[a-z]\)\s*", value) and section != "common_tools":
                flush()
                section = "essential_skills"
            if has_tools and re.match(r"noSQL\b", value, re.I):
                flush()
                section = "common_tools"
            if section:
                buffer.append(line)
        flush()
        # Continue only substantive sections, never a career diagram or empty
        # OCR cover page. A new heading/role on the next page takes precedence.
        active_section[doc] = section if any(heading(line)[0] for line in lines) else None
    return list(records.values())
