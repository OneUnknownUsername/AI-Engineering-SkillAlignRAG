"""Split a page's extracted text into readable blocks: title, sub-headings, paragraphs, bullet
points, and text read from images (OCR).

The verifier's page text is the native text followed by the OCR text, with all whitespace
collapsed to single spaces. Blocks are rebuilt from the original line breaks and given as
[start, end) positions in that page text, so what is shown is exactly the checked text and a
quote can still be highlighted by its position.
"""
from __future__ import annotations

import re

# Bullet characters, including the private-use glyphs PowerPoint uses for Wingdings bullets.
BULLET = re.compile(r"^(?:[•●▪∙◦‣○■□►▶✓✔➢➤→*–—-]|[-])\s*")
NUMBERED = re.compile(r"^\(?(?:\d{1,2}|[a-z]|[ivx]{1,4})[.)]\s+")
SENTENCE_END = (".", ":", "?", "!", ";")
JOINS = (",", "-", "&", "/", "(")
JOIN_WORDS = {"and", "or", "of", "the", "to", "a", "an", "in", "for", "with", "on", "by", "dan", "atau", "yang", "di", "untuk"}


def _lines(native: str, ocr: str) -> list[tuple[bool, int, int, str]]:
    """(is_ocr, start, end, text) of every non-empty line, as positions in the collapsed page text."""
    lines, position = [], 0
    for is_ocr, text in ((False, native or ""), (True, ocr or "")):
        for raw in text.split("\n"):
            line = " ".join(raw.split())
            if line:
                lines.append((is_ocr, position, position + len(line), line))
                position += len(line) + 1
    return lines


def _continues(previous: str, line: str) -> bool:
    """Whether a line is the PDF wrapping the previous line, rather than a new block."""
    if previous.endswith(SENTENCE_END):
        return False
    if previous.endswith(JOINS) or previous.rsplit(" ", 1)[-1].lower() in JOIN_WORDS:
        return True
    return not (line[:1].isupper() or line[:1].isdigit())


def page_blocks(native: str, ocr: str, title: str, page_text: str) -> list[dict]:
    """Blocks of {kind, start, end, ocr}; kind is title, heading, paragraph, bullet or numbered."""
    lines = _lines(native, ocr)
    # The lines must rebuild the page text exactly; otherwise show it as one plain block.
    if " ".join(line for *_, line in lines) != page_text:
        return [{"kind": "paragraph", "start": 0, "end": len(page_text), "ocr": False}] if page_text else []
    lines = [(is_ocr, start, end) for is_ocr, start, end, _ in lines]

    blocks, index = [], 0
    wanted = " ".join((title or "").split())
    if wanted:
        first = lines[0][1]
        for j, (is_ocr, _, end) in enumerate(lines):
            if is_ocr or end - first > len(wanted):
                break
            if page_text[first:end] == wanted:
                blocks.append({"kind": "title", "start": first, "end": end, "ocr": False})
                index = j + 1
                break

    current, bullet_next = None, False
    for is_ocr, start, end in lines[index:]:
        text = page_text[start:end]
        if current and current["ocr"] != is_ocr:
            current = None
        bullet = BULLET.match(text) if not is_ocr else None
        if bullet and bullet.end() == len(text):  # A bullet glyph alone on its line: the item follows.
            bullet_next, current = True, None
            continue
        if bullet or bullet_next:
            skip = bullet.end() if bullet else 0
            current = {"kind": "bullet", "start": start + skip, "end": end, "ocr": is_ocr}
            blocks.append(current)
        elif not is_ocr and NUMBERED.match(text):
            current = {"kind": "numbered", "start": start, "end": end, "ocr": False}
            blocks.append(current)
        elif current and _continues(page_text[current["start"]:current["end"]], text):
            current["end"] = end
        else:
            current = {"kind": "paragraph", "start": start, "end": end, "ocr": is_ocr}
            blocks.append(current)
        bullet_next = False

    # A short line that introduces a list, or a short label ending in a colon, reads as a sub-heading.
    for i, block in enumerate(blocks):
        if block["kind"] != "paragraph" or block["ocr"]:
            continue
        text = page_text[block["start"]:block["end"]]
        words = len(text.split())
        next_is_list = i + 1 < len(blocks) and blocks[i + 1]["kind"] in ("bullet", "numbered")
        if (text.endswith(":") and words <= 10) or (next_is_list and words <= 8 and not text.endswith((".", ",", ";"))):
            block["kind"] = "heading"
    return blocks
