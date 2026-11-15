"""Official outcome/synopsis windows and detection of slides that restate the CLOs."""
import re
from src.common import normalize

CLO_HEADING = re.compile(r'\bcourse\s+learning\s+outcomes?\b|\bC\s*L\s*O\s*[123]\b\s*[:.)-]', re.I)
SYNOPSIS = re.compile(r'\bcourse\s+synopsis\b|\bthis\s+course\s+(?:provides|addresses|aims|covers)', re.I)
OUTCOME_VERB = (r'(?:recommend|explain|practi[sc]e|construct|apply|analy[sz]e|evaluate|design|'
                r'develop|identify|demonstrate|implement|describe|understand|use|assess)\b')


def explicit_clo_statement(text: str) -> bool:
    text = normalize(text)
    if re.search(r'\bcourse\s+learning\s+outcomes?\b', text, re.I):
        return True
    return re.search(r'\bC\s*L\s*O\s*[123]\b\s*(?:[:.)-]\s*[A-Za-z]|' + OUTCOME_VERB + ')', text, re.I) is not None


def has_official_commitment(chunk: dict) -> bool:
    return chunk['evidence_level'] == 'CLO' and bool(
        explicit_clo_statement(chunk['verbatim_text_span']) or SYNOPSIS.search(chunk['verbatim_text_span']))


def clo_evidence_window(text: str) -> str:
    """Skip the administrative prefix without reconstructing or paraphrasing quotes."""
    match = CLO_HEADING.search(text)
    if match:
        return text[match.start():]
    match = SYNOPSIS.search(text)
    return text[match.start():] if match else text


def mark_slide_clo_pages(chunks: list[dict], catalog: dict) -> None:
    """Flag lecture pages that state learning outcomes, so the audit can compare them with the CI.

    The flag never makes a slide CLO evidence. Fields left by the earlier routing policy, which
    let such slides support CLO, are removed so old artifacts follow the current rule.
    """
    for course in catalog['courses'].values():
        course.pop('auxiliary_clo_pages', None)
        course['slide_clo_pages'] = []
    for chunk in chunks:
        chunk.pop('auxiliary_evidence_levels', None)
        chunk.pop('auxiliary_evidence_reason', None)
        chunk['restates_clo'] = chunk['evidence_level'] == 'Taught' and explicit_clo_statement(chunk['verbatim_text_span'])
        if chunk['restates_clo']:
            catalog['courses'][chunk['course_code']]['slide_clo_pages'].append(
                {'doc_id': chunk['doc_id'], 'pdf_page_no': chunk['pdf_page_no']})
