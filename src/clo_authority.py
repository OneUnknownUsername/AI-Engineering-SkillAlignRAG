"""CI authority for CLO (FR3): compare lecture-slide outcome statements with the CI.

The Course Information (CI) document alone decides CLO coverage. Slides that state learning
outcomes stay Taught evidence; this module only reports how their statements relate to the CI:
they repeat a CI statement (shown as corroboration), differ from the CI statement with the same
CLO number, or do not appear in the CI at all. Matching ignores case, spacing and punctuation
but is otherwise exact, so no model is involved and the same documents always give the same result.
"""
from __future__ import annotations

import re

from src.curriculum_scope import OUTCOME_VERB

WORD = re.compile(r'[A-Za-z0-9]+')
# "CLO2: Explain ..." or "CLO2 Explain ...", but not a bare label such as a schedule's "CLO2 Week 3".
NUMBERED = re.compile(r'\bCLO\s*(\d+)\b\s*(?:[:.)-]\s*(?=[A-Za-z])|(?=' + OUTCOME_VERB + '))', re.I)
# Listed outcomes after "...students should be able to:", e.g. "i. Define", "a) Analyze", "1. Explain".
LIST_START = re.compile(r'\bable\s+to\s*:', re.I)
LIST_ITEM = re.compile(r'(?:^|(?<=\s))(?:[ivx]{1,4}|[a-h]|\d{1,2})[.)]\s+(?=[A-Za-z])')
# The slide footer (page number, university and faculty names) that follows the last listed item.
FOOTER = re.compile(r'\s+(?:\d{1,3}\s+)?(?:UTM\b|UNIVERSITI TEKNOLOGI MALAYSIA|Faculty of Artificial Intelligence).*$', re.S)
MIN_WORDS, MAX_WORDS = 4, 40


def page_key(chunk: dict) -> str:
    return f"{chunk['course_code']}::{chunk['doc_id']}::{chunk['pdf_page_no']}"


def clip(text: str) -> str:
    return ' '.join(FOOTER.sub('', text).split()[:MAX_WORDS])


def find_span(statement: str, page: str) -> str | None:
    """Return the page's own characters for `statement`, ignoring case, spacing and punctuation."""
    words = WORD.findall(statement)
    if len(words) < MIN_WORDS:
        return None
    pattern = r'(?<![A-Za-z0-9])' + r'[^A-Za-z0-9]+'.join(map(re.escape, words)) + r'(?![A-Za-z0-9])'
    match = re.search(pattern, page, re.I)
    return match.group() if match else None


def ci_statements(ci_pages: list[tuple[dict, str]]) -> list[dict]:
    """Numbered CLO statements from the CI's extracted tables, quoted from the CI page text."""
    found = {}
    for chunk, page in ci_pages:
        for row in (chunk.get('tables_markdown') or '').splitlines():
            cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
            for label, text in zip(cells, cells[1:]):
                match = re.fullmatch(r'CLO\s*(\d+)', label, re.I)
                if match and len(WORD.findall(text)) >= MIN_WORDS and int(match.group(1)) not in found:
                    quote = find_span(text, page)
                    found[int(match.group(1))] = {
                        'clo': f'CLO{int(match.group(1))}', 'doc_id': chunk['doc_id'], 'pdf_page_no': chunk['pdf_page_no'],
                        'statement': quote or ' '.join(text.split()), 'quoted_from_page': quote is not None}
    return [found[number] for number in sorted(found)]


def slide_statements(page: str) -> tuple[dict[int, str], list[str]]:
    """Numbered statements ("CLO2: ...") and listed outcome items on one slide page."""
    numbered = {}
    labels = list(NUMBERED.finditer(page))
    for i, match in enumerate(labels):
        end = labels[i + 1].start() if i + 1 < len(labels) else len(page)
        text = clip(page[match.end():end])
        if len(WORD.findall(text)) >= MIN_WORDS:
            numbered.setdefault(int(match.group(1)), text)
    items = []
    start = LIST_START.search(page)
    if start:
        parts = LIST_ITEM.split(page[start.end():])
        items = [clip(part) for part in parts[1:] if len(WORD.findall(part)) >= MIN_WORDS]
    return numbered, items


def compare_page(chunk: dict, page: str, ci: list[dict], ci_pages: list[tuple[dict, str]]) -> dict:
    """Label each outcome statement on a slide page against the course's CI."""
    entry = {'doc_id': chunk['doc_id'], 'pdf_page_no': chunk['pdf_page_no'], 'statements': []}
    numbered, items = slide_statements(page)
    if not ci_pages:
        entry['statements'] = [{'statement': text, 'status': 'no_ci'}
                               for text in [*(f'CLO{n}: {t}' for n, t in sorted(numbered.items())), *items]]
        return entry
    repeated = set()
    for statement in ci:
        span = find_span(statement['statement'], page)
        if span:
            repeated.add(statement['clo'])
            entry['statements'].append({'statement': span, 'status': 'repeats_ci', **ci_reference(statement)})
    by_clo = {s['clo']: s for s in ci}
    for number, text in sorted(numbered.items()):
        clo = f'CLO{number}'
        if clo in repeated:
            continue
        if clo in by_clo:
            entry['statements'].append({'statement': f'{clo}: {text}', 'status': 'differs_from_ci', **ci_reference(by_clo[clo])})
        else:
            entry['statements'].append({'statement': f'{clo}: {text}', 'status': 'not_in_ci'})
    for item in items:
        match = next(((c, p) for c, p in ci_pages if find_span(item, p)), None)
        within = next((s for s in ci if find_span(s['statement'], item)), None)
        if within and within['clo'] in repeated:
            continue  # Already reported as a repeated CI statement.
        if match or within:
            reference = ci_reference(within) if within else {'ci_doc_id': match[0]['doc_id'], 'ci_pdf_page_no': match[0]['pdf_page_no']}
            entry['statements'].append({'statement': item, 'status': 'repeats_ci', **reference})
        else:
            entry['statements'].append({'statement': item, 'status': 'not_in_ci'})
    return entry


def ci_reference(statement: dict) -> dict:
    return {'ci_clo': statement['clo'], 'ci_statement': statement['statement'],
            'ci_doc_id': statement['doc_id'], 'ci_pdf_page_no': statement['pdf_page_no']}


def course_pages(course: str, chunks: list[dict], lookup: dict) -> tuple[list, list]:
    """(CI pages, slide pages that state outcomes), each as (chunk, verbatim page text)."""
    ordered = sorted((c for c in chunks if c['course_code'] == course), key=lambda c: (c['doc_id'], c['pdf_page_no']))
    ci = [(c, lookup.get(page_key(c), '')) for c in ordered if c['evidence_level'] == 'CLO']
    slides = [(c, lookup.get(page_key(c), '')) for c in ordered if c.get('restates_clo')]
    return ci, slides


def compare_with_ci(course: str, ci_available: bool, chunks: list[dict], lookup: dict) -> dict:
    ci_pages, slides = course_pages(course, chunks, lookup)
    ci_pages = ci_pages if ci_available else []
    ci = ci_statements(ci_pages)
    return {'ci_available': bool(ci_pages), 'ci_statements': ci,
            'slide_pages': [compare_page(chunk, page, ci, ci_pages) for chunk, page in slides]}


def corroborating_slides(quote: str, course: str, chunks: list[dict], lookup: dict) -> list[dict]:
    """Slides that repeat a verified CI quote word for word; shown beside the CI, never instead of it."""
    _, slides = course_pages(course, chunks, lookup)
    return [{'doc_id': chunk['doc_id'], 'pdf_page_no': chunk['pdf_page_no'], 'slide_quote': span}
            for chunk, page in slides if (span := find_span(quote, page))]
