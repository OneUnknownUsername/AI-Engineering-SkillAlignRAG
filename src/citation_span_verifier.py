"""Fail-closed citation identity, canonical substring and local entailment gates."""
from __future__ import annotations
import re
import math
from src.common import evidence_levels
from src.config import AuditConfig
from src.curriculum_scope import explicit_clo_statement
from src.skill_hypotheses import atomic_hypotheses, CORE_DOMAIN_TERMS

PUNCTUATION = str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-', '−': '-'})


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    chars, offsets = [], []
    for i, char in enumerate(text):
        char = char.translate(PUNCTUATION)
        if char.isspace():
            if chars and chars[-1] != ' ':
                chars.append(' ')
                offsets.append(i)
        else:
            chars.append(char)
            offsets.append(i)
    if chars and chars[-1] == ' ':
        chars.pop()
        offsets.pop()
    return ''.join(chars), offsets


def canonical_span(quote: str, page: str) -> tuple[str | None, bool]:
    normalized, offsets = normalize_with_offsets(page)
    needle, _ = normalize_with_offsets(quote)
    if len(needle) >= 20 and needle in normalized:
        start = normalized.index(needle)
        return page[offsets[start]:offsets[start + len(needle) - 1] + 1], False
    if re.search(r'\.{3}|…', quote):
        segments = sorted(re.split(r'\.{3}|…', quote), key=lambda s: len(normalize_with_offsets(s)[0]), reverse=True)
        # Only the longest contiguous segment is eligible for snapping.
        segment, _ = normalize_with_offsets(segments[0])
        if len(segment) >= 35 and segment in normalized:
            start = normalized.index(segment)
            return page[offsets[start]:offsets[start + len(segment) - 1] + 1], True
    return None, False


def expand_short_quote(quote: str, page: str, chunk: str) -> str | None:
    """Expand a verified 20–44 character seed to its canonical sentence/bullet.

    Boundaries and returned characters come exclusively from the lookup page.
    If expansion cannot reach 45 characters, the caller can retain the verified seed.
    """
    normalized, offsets = normalize_with_offsets(page)
    needle, _ = normalize_with_offsets(quote)
    if not 20 <= len(needle) < 45:
        return None
    # Hard boundaries enclose a bullet or paragraph. PDF stores may flatten line breaks,
    # but retain bullet glyphs. Numbered items are also recognized after PDF flattening.
    hard = {0, len(page)}
    for boundary in re.finditer(r'\r?\n[ \t]*\r?\n|[•●▪◦‣]|(?<!\w)\d{1,2}[.)][ \t]+(?=[A-Z])|(?m:^[ \t]*[-*][ \t]+)', page):
        hard.add(boundary.start())
        if '\n' in boundary.group():
            hard.add(boundary.end())
    for match in re.finditer(re.escape(needle), normalized):
        left, right = offsets[match.start()], offsets[match.end()-1] + 1
        block_start = max(b for b in hard if b <= left)
        block_end = min(b for b in hard if b >= right)
        sentence_ends = [block_start, block_end]
        for end in re.finditer(r'[.!?]["”’)]*(?=\s|$)', page[block_start:block_end]):
            sentence_ends.append(block_start + end.end())
        start = max(b for b in sentence_ends if b <= left)
        end = min(b for b in sentence_ends if b >= right)
        # Prefer the enclosing sentence; a multi-sentence bullet is the fallback.
        for start, end in ((start, end), (block_start, block_end)):
            candidate = page[start:end].strip()
            if len(normalize_with_offsets(candidate)[0]) >= 45:
                in_chunk, _ = canonical_span(candidate, chunk)
                if in_chunk is not None:
                    return candidate
    return None


def pedagogical_boundary(level: str, skill: dict, candidate: dict, quote: str) -> str | None:
    text = (candidate.get('slide_or_section_title', '') + '\n' + quote).lower()
    if level == 'CLO' and not (re.search(r'learning outcome|course synopsis|course learning|\bclo\s*\d|\btlo\s*\d|upon completion|on completion', text) or explicit_clo_statement(candidate.get('verbatim_text_span', ''))):
        return 'No explicit outcome or synopsis commitment'
    if level == 'Assessed' and not re.search(r'\b(assignment|question|task|rubric|marks|students? must|you (?:must|are required)|implement|analyse|analyze|evaluate|develop|design|create|compare|explain|demonstrate)\b', text):
        return 'No assessed task or criterion'
    if re.search(r'^(references|bibliography)\b', text.strip()):
        return 'Bibliographic material'
    if level == 'Taught':
        if re.search(r'^(source:|figure credit|history of|timeline)', text.strip()) or re.search(r'\b(history|timeline)\b', candidate.get('slide_or_section_title', '').lower()):
            return 'Credit or historical mention'
        if re.search(r'spotify|sephora|booking\.com|source: amazon aws', text) and not re.search(r'algorithm|step\s*\d|procedure|gradient|formula|pseudocode|def |fit\(|transform\(', text):
            return 'Consumer example or figure credit without underlying method'
        if re.search(r'font size|turnitin|plagiarism policy', text):
            return 'Generic administrative content'
        if candidate.get('course_code') == 'SAIA1013' and skill['skill_id'] in ('S04', 'S05', 'S06', 'S07'):
            if not re.search(r'algorithm|step\s*\d|loss function|gradient|train_test_split|cross.valid|regulariz|hyperparameter', text):
                return 'Introductory modelling recap in Ethics without methods'
    if skill['skill_id'] == 'S11':
        if not re.search(r'\b(models?|predictions?|inference)\b', text) or not re.search(r'\b(deploy\w*|serv\w*|packag\w*|endpoint|rest|flask|fastapi)\b', text):
            return 'No trained-model service packaging evidence'
    if skill['skill_id'] == 'S12' and not re.search(r'mlops|ci/cd|ci.cd|container|docker|kubernetes|model version|production.*monitor|pipeline.*automat|continuous.*deploy', text):
        return 'No production MLOps pipeline evidence'
    return None


class NLIVerifier:
    def __init__(self, config: AuditConfig):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        if not torch.cuda.is_available():
            raise RuntimeError('NLI verification requires CUDA')
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(config.nli_model, **config.model_options())
        self.model = AutoModelForSequenceClassification.from_pretrained(config.nli_model, **config.model_options()).to('cuda:0').eval()
        self.labels = {int(i): str(label).lower() for i, label in self.model.config.id2label.items()}
        if set(self.labels.values()) != {'entailment', 'neutral', 'contradiction'}:
            raise ValueError(f'NLI model must declare semantic id2label; got {self.labels}')

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[dict]:
        # Score all atomic facets and both premise variants in one GPU batch.
        for premise, hypothesis in pairs:
            length = len(self.tokenizer.encode(premise, hypothesis, add_special_tokens=True))
            if length > min(self.tokenizer.model_max_length, 512):
                raise ValueError('NLI premise exceeds model context; quote cannot be silently truncated')
        inputs = self.tokenizer([p for p, _ in pairs], [h for _, h in pairs],
                                padding=True, return_tensors='pt', truncation=False).to('cuda:0')
        with self.torch.inference_mode():
            probabilities = self.model(**inputs).logits.softmax(dim=-1).cpu().tolist()
        return [{**{self.labels[i]: float(p) for i, p in enumerate(row)},
                 'non_contradiction_score': sum(p for i, p in enumerate(row)
                                                if self.labels[i] != 'contradiction')}
                for row in probabilities]

    def score(self, title: str, quote: str, context: str, hypothesis: str) -> dict:
        return self.score_pairs([(title + '\n' + quote if title else quote, hypothesis)])[0]


class CitationSpanVerifier:
    def __init__(self, lookup: dict, nli):
        self.lookup, self.nli = lookup, nli

    def verify(self, course: str, level: str, skill: dict, draft: dict, candidates: list[dict]) -> dict:
        result = {'gate_6a': 'not_run', 'gate_6b': 'not_run', 'final_classification': 'Not Found', 'verified_citation': None}
        if draft.get('draft_classification') != 'Supported':
            return result
        result['gate_6a'] = 'rejected'
        rank = draft.get('candidate_rank_selected')
        top_three = candidates[:3]
        if type(rank) is not int or not 1 <= rank <= len(top_three):
            return {**result, 'rejection_reason': 'Invalid selected candidate rank'}
        if not isinstance(draft.get('doc_id'), str) or type(draft.get('pdf_page_no')) is not int:
            return {**result, 'rejection_reason': 'Invalid citation identity'}
        cited = (course, draft['doc_id'], draft['pdf_page_no'])
        identities = [(h.get('course_code'), h['doc_id'], h['pdf_page_no']) for h in top_three]
        if cited not in identities:
            return {**result, 'rejection_reason': 'Citation is outside the retrieved Top-3'}
        quote = draft.get('verbatim_quote')
        if not isinstance(quote, str):
            return {**result, 'rejection_reason': 'Missing quote'}
        normalized_quote, _ = normalize_with_offsets(quote)
        if len(normalized_quote) < 20:
            return {**result, 'rejection_reason': 'Quote shorter than 20 normalized characters'}
        eligible = [(i, h) for i, h in enumerate(top_three, 1)
                    if h.get('course_code') == course and level in evidence_levels(h)]
        if not eligible:
            return {**result, 'rejection_reason': 'Wrong-level citation; no same-course/level Top-3 candidates'}
        # Prefer the cited page, then resolve only within this request's same-level Top-3.
        eligible.sort(key=lambda item: (identities[item[0]-1] != cited, item[0] != rank, item[0]))
        attempts = []
        resolved = None
        for candidate_rank, hit in eligible:
            attempt = {'candidate_rank': candidate_rank, 'doc_id': hit['doc_id'], 'pdf_page_no': hit['pdf_page_no']}
            attempts.append(attempt)
            page = self.lookup.get(f"{course}::{hit['doc_id']}::{hit['pdf_page_no']}")
            if not isinstance(page, str):
                attempt['status'] = 'missing_lookup_page'
                continue
            seed, snapped = canonical_span(quote, page)
            if seed is None:
                attempt['status'] = 'quote_not_on_page'
                continue
            if canonical_span(seed, hit['verbatim_text_span'])[0] is None:
                attempt['status'] = 'quote_not_in_candidate_chunk'
                continue
            short = len(normalize_with_offsets(seed)[0]) < 45
            expanded = expand_short_quote(seed, page, hit['verbatim_text_span']) if short else None
            # A real 20–44 character bullet remains valid even if it cannot grow to 45.
            canonical = expanded or seed
            attempt['status'] = 'matched'
            resolved = (candidate_rank, hit, canonical, snapped, expanded, short)
            break
        result['gate_6a_attempts'] = attempts
        if resolved is None:
            return {**result, 'rejection_reason': 'Quote not a canonical page and chunk substring in same-course/level Top-3'}
        resolved_rank, hit, canonical, snapped, expanded, short = resolved
        changed = resolved_rank != rank or identities[resolved_rank-1] != cited
        result.update(gate_6a='passed', ellipsis_snapped=snapped, gate_6b='rejected',
                      resolved_candidate_rank=resolved_rank, citation_resolved=changed,
                      canonical_verbatim_quote=canonical, short_quote_expanded=expanded is not None,
                      short_quote_retained=short and expanded is None)
        if changed:
            result['citation_resolution'] = {
                'original_candidate_rank': rank, 'original_doc_id': draft['doc_id'],
                'original_pdf_page_no': draft['pdf_page_no'], 'resolved_candidate_rank': resolved_rank,
                'resolved_doc_id': hit['doc_id'], 'resolved_pdf_page_no': hit['pdf_page_no'],
                'reason': 'verbatim_match_in_same_course_level_top3'}
        if expanded is not None:
            result['short_quote_expansion'] = {'original_quote': quote, 'canonical_quote': canonical,
                                                'source': 'verbatim_lookup_store', 'target_length': 45}
        boundary = pedagogical_boundary(level, skill, hit, canonical)
        if boundary:
            return {**result, 'rejection_reason': boundary}
        hypotheses = atomic_hypotheses(skill)
        title = hit.get('slide_or_section_title', '')
        # This factual provenance label supplies the subject in the benchmark hypothesis.
        # It adds no assertion of teaching, assessment, or skill support.
        variants = [('quote', 'Course material:\n' + canonical),
                    ('title_and_quote', 'Course material:\n' + title + '\n' + canonical)]
        pairs = [(premise, hypothesis) for hypothesis in hypotheses for _, premise in variants]
        try:
            if hasattr(self.nli, 'score_pairs'):
                values = self.nli.score_pairs(pairs)
            else:
                # Test doubles and compatible custom verifiers may implement scalar score.
                values = [self.nli.score('', premise, '', hypothesis) for premise, hypothesis in pairs]
        except ValueError as exc:
            return {**result, 'rejection_reason': str(exc)}
        if len(values) != len(pairs):
            return {**result, 'rejection_reason': 'Incomplete atomic NLI results'}
        trials = []
        for i, scores in enumerate(values):
            probabilities = [scores.get(k) for k in ('entailment', 'neutral', 'contradiction')]
            if any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities) or abs(sum(probabilities)-1) > .001:
                return {**result, 'rejection_reason': 'Invalid NLI probabilities'}
            trials.append({'hypothesis': hypotheses[i // 2], 'premise_variant': variants[i % 2][0],
                           **scores, 'non_contradiction_score': scores['entailment'] + scores['neutral']})
        # All probabilities used by the fallback must come from this same winning pair.
        winner = max(trials, key=lambda trial: trial['entailment'])
        quote_terms = set(re.findall(r'[a-z][a-z0-9]+', canonical.lower()))
        domain_terms = sorted(quote_terms & set(CORE_DOMAIN_TERMS[skill['skill_id']].split()))
        maximum = winner['entailment']
        strong = maximum >= .40
        domain_fallback = (maximum >= .20 and winner['contradiction'] < .15
                           and winner['non_contradiction_score'] >= .85 and len(domain_terms) >= 2)
        result.update(nli_premise_provenance='Course material:', nli_scores=winner, atomic_nli_scores=trials, max_entailment=maximum,
                      shared_core_domain_terms=domain_terms,
                      nli_acceptance_rule='entailment_0.40' if strong else 'domain_aligned_0.20' if domain_fallback else None)
        if not (strong or domain_fallback):
            return {**result, 'rejection_reason': 'Atomic entailment and domain-alignment thresholds not met'}
        result.update(gate_6b='passed', final_classification='Supported', verified_citation={
            'doc_id': hit['doc_id'], 'pdf_page_no': hit['pdf_page_no'], 'verbatim_quote': canonical})
        return result
