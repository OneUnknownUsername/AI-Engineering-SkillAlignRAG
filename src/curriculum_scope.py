"""Source-level routing and contiguous official outcome/synopsis windows."""
import re
from src.common import normalize

CLO_HEADING = re.compile(r'\bcourse\s+learning\s+outcomes?\b|\bC\s*L\s*O\s*[123]\b\s*[:.)-]', re.I)
SYNOPSIS = re.compile(r'\bcourse\s+synopsis\b|\bthis\s+course\s+(?:provides|addresses|aims|covers)', re.I)


def explicit_clo_statement(text: str) -> bool:
    text = normalize(text)
    if re.search(r'\bcourse\s+learning\s+outcomes?\b', text, re.I):
        return True
    return re.search(
        r'\bC\s*L\s*O\s*[123]\b\s*(?:[:.)-]\s*[A-Za-z]|'
        r'(?:recommend|explain|practi[sc]e|construct|apply|analy[sz]e|evaluate|design|'
        r'develop|identify|demonstrate|implement|describe|understand|use|assess)\b)', text, re.I) is not None


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


def refresh_auxiliary_clo_pages(chunks: list[dict], catalog: dict) -> None:
    """Recompute memberships from physical source levels, including old artifacts."""
    for course in catalog['courses'].values():
        course['auxiliary_clo_pages'] = []
    for chunk in chunks:
        course = catalog['courses'][chunk['course_code']]
        eligible = (chunk['evidence_level'] == 'Taught' and course['level_availability']['CLO']
                    and explicit_clo_statement(chunk['verbatim_text_span']))
        chunk['auxiliary_evidence_levels'] = ['CLO'] if eligible else []
        if eligible:
            chunk.update(auxiliary_evidence_reason='explicit_clo_definition_or_header', indexable=True, skip_reason=None)
            course['auxiliary_clo_pages'].append({'doc_id': chunk['doc_id'], 'pdf_page_no': chunk['pdf_page_no'],
                                                  'source_evidence_level': 'Taught'})
        else:
            chunk.pop('auxiliary_evidence_reason', None)
