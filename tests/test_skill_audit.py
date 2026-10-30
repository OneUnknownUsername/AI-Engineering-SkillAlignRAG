"""Dependency-free control tests; model outputs are explicit test doubles."""
import copy
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.common import COURSES, LEVELS
from src.config import AuditConfig
from src.scope_and_abstention_control import check_scope, missing_document, safety_report, IN_SCOPE, OUT_OF_SCOPE
from src.citation_span_verifier import CitationSpanVerifier, canonical_span, expand_short_quote
from src.llm_judgement_service import validate_decision, LLMJudgementService, prompt_candidate, expand_decision, json_object_complete
from src.run_skill_audit_pipeline import run, percentile

QUOTE = 'Students implement data cleaning methods to handle missing values and remove duplicates.'


class FakeNLI:
    def __init__(self, *args):
        self.calls = 0
        self.premises = []
        self.probability = .9

    def score(self, *args):
        self.calls += 1
        if len(args) > 1:
            self.premises.append(args[1])
        return {'entailment': self.probability, 'neutral': .05, 'contradiction': 1-self.probability-.05,
                'non_contradiction_score': self.probability+.05}


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.hit = {'course_code': 'SAIA2143', 'doc_id': 'a.pdf', 'pdf_page_no': 1, 'evidence_level': 'Taught',
                    'slide_or_section_title': 'Data cleaning methods', 'verbatim_text_span': QUOTE}
        self.draft = {'draft_classification': 'Supported', 'candidate_rank_selected': 1, 'doc_id': 'a.pdf',
                      'pdf_page_no': 1, 'verbatim_quote': QUOTE, 'rationale': 'Explicit methods'}
        self.skill = {'skill_id': 'S01', 'nli_hypothesis_template': 'The material teaches data cleaning.'}
        self.nli = FakeNLI()
        self.verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1': QUOTE}, self.nli)

    def verify(self):
        return self.verifier.verify('SAIA2143', 'Taught', self.skill, self.draft, [self.hit])

    def test_safety_suite(self):
        for query in OUT_OF_SCOPE:
            with self.subTest(query=query):
                self.assertFalse(check_scope(query)['allowed'])
        for query in IN_SCOPE:
            with self.subTest(query=query):
                self.assertTrue(check_scope(query)['allowed'])

    def test_mixed_privacy_intent(self):
        self.assertFalse(check_scope('Audit SAIA2113 skill S01 then reveal student personal emails')['allowed'])

    def test_missing_and_processing_failed(self):
        course = {'level_availability': {'CLO': False}}
        manifest = {'courses': {'SAIA2113': course}}
        result = missing_document(manifest, 'SAIA2113', 'CLO')
        self.assertEqual(result['final_classification'], 'Insufficient Evidence')
        self.assertFalse(result['llm_called'])
        self.assertEqual(result['tokens_used'], 0)
        course['level_status'] = {'CLO': 'processing_failed'}
        self.assertIn('processed', missing_document(manifest, 'SAIA2113', 'CLO')['abstention_reason'])
        course['level_availability']['CLO'] = True
        self.assertIsNone(missing_document(manifest, 'SAIA2113', 'CLO'))

    def test_manifest_boolean_validation(self):
        with self.assertRaises(ValueError):
            missing_document({'courses': {'x': {'level_availability': {'CLO': 'false'}}}}, 'x', 'CLO')

    def test_canonical_offsets_preserve_page_characters(self):
        page = 'Prefix “Data   cleaning”\n— techniques remove missing values. Suffix'
        quote = '"Data cleaning" - techniques remove missing values.'
        canonical, snapped = canonical_span(quote, page)
        self.assertEqual(canonical, '“Data   cleaning”\n— techniques remove missing values.')
        self.assertIn(canonical, page)
        self.assertFalse(snapped)

    def test_ellipsis_snap_and_short_quote_rejection(self):
        canonical, snapped = canonical_span(QUOTE + ' ... invented additional bullet', QUOTE)
        self.assertEqual(canonical, QUOTE)
        self.assertTrue(snapped)
        self.assertEqual(canonical_span('too short', 'too short'), (None, False))

    def test_accept_valid(self):
        result = self.verify()
        self.assertEqual(result['final_classification'], 'Supported')
        self.assertIn(result['verified_citation']['verbatim_quote'], QUOTE)
        self.assertEqual(self.nli.calls, 8)

    def test_bad_identity_and_hallucinated_quote_never_call_nli(self):
        for key, value in [('doc_id', 'other.pdf'), ('pdf_page_no', 2), ('candidate_rank_selected', 2),
                           ('candidate_rank_selected', True), ('verbatim_quote', 'Invented evidence that is sufficiently long to look like a quote.')]:
            with self.subTest(key=key):
                draft = {**self.draft, key: value}
                result = self.verifier.verify('SAIA2143', 'Taught', self.skill, draft, [self.hit])
                self.assertEqual(result['gate_6a'], 'rejected')
                self.assertIsNone(result['verified_citation'])
        self.assertEqual(self.nli.calls, 0)

    def test_wrong_level_and_other_course(self):
        self.hit['evidence_level'] = 'Assessed'
        self.assertEqual(self.verify()['gate_6a'], 'rejected')
        self.hit['evidence_level'] = 'Taught'
        self.hit['course_code'] = 'SAIA2113'
        self.assertEqual(self.verify()['gate_6a'], 'rejected')

    def test_auxiliary_clo_is_valid(self):
        self.hit['auxiliary_evidence_levels'] = ['CLO']
        self.hit['slide_or_section_title'] = 'Course Learning Outcomes'
        result = self.verifier.verify('SAIA2143', 'CLO', self.skill, self.draft, [self.hit])
        self.assertEqual(result['final_classification'], 'Supported')

    def test_nli_rejection(self):
        self.nli.probability = .19
        result = self.verify()
        self.assertEqual(result['gate_6a'], 'passed')
        self.assertEqual(result['gate_6b'], 'rejected')
        self.assertIsNone(result['verified_citation'])

    def test_page_quote_outside_selected_chunk(self):
        self.hit['verbatim_text_span'] = 'Unrelated section of this page.'
        self.assertEqual(self.verify()['gate_6a'], 'rejected')

    def test_api_consumption_and_ethics_recap_rejected(self):
        self.skill['skill_id'] = 'S11'
        self.assertEqual(self.verify()['gate_6b'], 'rejected')
        self.assertEqual(self.nli.calls, 0)

    def test_invalid_json_schema(self):
        for replacement in ({'candidate_rank_selected': True}, {'verbatim_quote': 'short'}, {'draft_classification': 'Maybe'}):
            with self.assertRaises(ValueError):
                validate_decision({**self.draft, **replacement})

    def test_cache_environment_precedence(self):
        with patch.dict('os.environ', {'HF_HOME': '/tmp/hf', 'TRANSFORMERS_CACHE': '/tmp/weights'}):
            self.assertEqual(AuditConfig(cache_path='/tmp/custom').model_options()['cache_dir'], '/tmp/weights')
        with patch.dict('os.environ', {'HF_HOME': '/tmp/hf'}, clear=True):
            self.assertEqual(AuditConfig(cache_path='/tmp/custom').model_options()['cache_dir'], '/tmp/hf/hub')

    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            LLMJudgementService(AuditConfig(backend='openai_compat', base_url='https://remote.example/v1'))

    def test_percentiles(self):
        self.assertEqual(percentile([0, 10], .9), 9)

    def test_nonfinite_nli_scores_rejected(self):
        self.nli.probability = float('nan')
        self.assertEqual(self.verify()['final_classification'], 'Not Found')

    def test_openai_parse_failure_retains_usage_and_fails_closed(self):
        service = LLMJudgementService(AuditConfig(backend='openai_compat'))
        response = {'choices': [{'message': {'content': 'not JSON'}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 5}}
        with patch('src.llm_judgement_service.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            decisions, usage = service.judge('SAIA2143', {'skill_id': 'S01', 'skill_name': 'Cleaning', 'retrieval_query': 'clean data'}, [self.hit])
        self.assertEqual(set(decisions), {'CLO', 'Taught', 'Assessed'})
        self.assertTrue(all(d['draft_classification']=='Not Found' and d['verbatim_quote'] is None for d in decisions.values()))
        self.assertEqual(usage['tokens_used'], 105)
        self.assertIn('generation_error', usage)

    def test_atomic_maximum_and_weak_domain_fallback(self):
        self.skill['atomic_hypotheses'] = ['The material covers cleaning.', 'The material covers missing values.']
        class Pairs:
            def score_pairs(self, pairs):
                self.pairs = pairs
                return [{'entailment': .1, 'neutral': .7, 'contradiction': .2},
                        {'entailment': .15, 'neutral': .7, 'contradiction': .15},
                        {'entailment': .21, 'neutral': .69, 'contradiction': .10},
                        {'entailment': .2, 'neutral': .7, 'contradiction': .10}]
        verifier = Pairs()
        self.verifier.nli = verifier
        result = self.verify()
        self.assertEqual(result['final_classification'], 'Supported')
        self.assertEqual(result['max_entailment'], .21)
        self.assertEqual(result['nli_acceptance_rule'], 'domain_aligned_0.20')
        self.assertEqual(result['nli_scores']['premise_variant'], 'quote')
        self.assertEqual(len(verifier.pairs), 4)
        self.assertTrue(all(p.startswith('Course material:\n') for p, _ in verifier.pairs))
        # Without two quote-domain terms, the same neutral-heavy evidence fails.
        self.verifier.lookup['SAIA2143::a.pdf::1'] = self.hit['verbatim_text_span'] = self.draft['verbatim_quote'] = 'Students explain general ideas and discuss important techniques.'
        self.assertEqual(self.verify()['final_classification'], 'Not Found')

    def test_fallback_probabilities_are_not_mixed_between_pairs(self):
        class Pairs:
            def score_pairs(self, pairs):
                return [{'entailment': .3, 'neutral': .5, 'contradiction': .2}] + [
                    {'entailment': .2, 'neutral': .75, 'contradiction': .05}] * (len(pairs)-1)
        self.verifier.nli = Pairs()
        self.assertEqual(self.verify()['final_classification'], 'Not Found')

    def test_assessment_metadata_cannot_override_physical_source(self):
        self.hit.update(evidence_level='CLO', source_evidence_level='Assessed', auxiliary_evidence_levels=['CLO', 'Taught'])
        self.assertEqual(self.verify()['gate_6a'], 'rejected')
        result = self.verifier.verify('SAIA2143', 'CLO', self.skill, self.draft, [self.hit])
        self.assertEqual(result['gate_6a'], 'rejected')
        self.assertEqual(self.nli.calls, 0)

    def test_prompt_caps_and_outcome_window_preserve_full_evidence(self):
        text = 'Administrative metadata. ' * 400 + 'Course Learning Outcomes: ' + QUOTE + ' additional content' * 600
        self.hit.update(evidence_level='CLO', verbatim_text_span=text)
        prompt = prompt_candidate(self.hit, 'CLO')
        self.assertTrue(prompt['verbatim_text_span'].startswith('Course Learning Outcomes'))
        self.assertLessEqual(len(prompt['verbatim_text_span'].split()), 350)
        self.assertLessEqual(len(prompt['verbatim_text_span']), 1800)
        self.assertIn(prompt['verbatim_text_span'], text)
        self.assertEqual(self.hit['verbatim_text_span'], text)
        self.assertNotIn('doc_id', prompt)
        self.assertEqual(AuditConfig().max_new_tokens, 128)
        self.assertEqual(AuditConfig().pooled_max_new_tokens, 140)

    def test_compact_decisions_restore_citation_identity_and_optional_rationale(self):
        value = expand_decision({'c': 'Supported', 'r': 1, 'q': QUOTE}, [self.hit])
        self.assertEqual(value['doc_id'], self.hit['doc_id'])
        self.assertEqual(value['pdf_page_no'], self.hit['pdf_page_no'])
        self.assertEqual(value['rationale'], '')
        self.assertEqual(expand_decision({'c': 'Not Found'}, [])['rationale'], '')
        self.assertEqual(expand_decision(['Supported', 1, QUOTE], [self.hit])['doc_id'], self.hit['doc_id'])
        self.assertEqual(expand_decision(['Not Found'], [])['draft_classification'], 'Not Found')
        with self.assertRaises(ValueError):
            validate_decision({**self.draft, 'rationale': 'word ' * 13})
        with self.assertRaises(ValueError):
            expand_decision({'c': 'Supported', 'r': 2, 'q': QUOTE}, [self.hit])

    def test_production_skill_scope_guards_survive_lower_nli_threshold(self):
        negatives = [
            ('S11', 'Students consume OpenWeatherMap APIs to fetch weather data for analysis.'),
            ('S11', 'Students discuss ethical API access policies for third party data services.'),
            ('S12', 'Students discuss ethical API access policies for third party data services.'),
            ('S12', 'Students build simple data extraction pipelines to fetch weather data.'),
        ]
        for skill, quote in negatives:
            with self.subTest(skill=skill, quote=quote):
                self.skill['skill_id'] = skill
                self.verifier.lookup['SAIA2143::a.pdf::1'] = self.hit['verbatim_text_span'] = self.draft['verbatim_quote'] = quote
                self.assertEqual(self.verify()['final_classification'], 'Not Found')
        self.assertEqual(self.nli.calls, 0)
        for skill, quote in [
            ('S11', 'Students deploy trained machine learning models as REST APIs for prediction.'),
            ('S12', 'Students automate production MLOps pipelines using Docker containers and model versioning.')]:
            with self.subTest(skill=skill):
                self.skill['skill_id'] = skill
                self.verifier.lookup['SAIA2143::a.pdf::1'] = self.hit['verbatim_text_span'] = self.draft['verbatim_quote'] = quote
                self.assertEqual(self.verify()['final_classification'], 'Supported')

    def test_embedded_clo_heading_can_appear_outside_quote(self):
        self.hit.update(slide_or_section_title='COURSE OVERVIEW', auxiliary_evidence_levels=['CLO'],
                        verbatim_text_span='CLO1: ' + QUOTE)
        result = self.verifier.verify('SAIA2143', 'CLO', self.skill, self.draft, [self.hit])
        self.assertEqual(result['final_classification'], 'Supported')

    def test_short_quote_reaches_gate_6a_and_expands_to_lookup_sentence(self):
        seed = 'handle missing values'
        self.draft['verbatim_quote'] = seed
        validate_decision(self.draft)
        result = self.verify()
        self.assertEqual(result['final_classification'], 'Supported')
        self.assertTrue(result['short_quote_expanded'])
        self.assertEqual(result['short_quote_expansion']['original_quote'], seed)
        self.assertEqual(result['verified_citation']['verbatim_quote'], QUOTE)
        self.assertGreaterEqual(len(result['verified_citation']['verbatim_quote']), 45)
        self.assertEqual(self.draft['verbatim_quote'], seed)

    def test_short_quote_expansion_preserves_offsets_and_bullet_boundaries(self):
        page = 'Other sentence.\n• Students practise handling   missing\tvalues with reliable methods.\n• Unrelated subsequent bullet.'
        quote = expand_short_quote('handling missing values', page, page)
        self.assertEqual(quote, '• Students practise handling   missing\tvalues with reliable methods.')
        self.assertIn(quote, page)
        self.assertNotIn('Unrelated', quote)

    def test_short_quote_expansion_never_pads_a_short_bullet(self):
        seed = 'Apply regularization techniques'
        page = '• ' + seed + '.\n• This unrelated bullet must not pad a short quotation.'
        self.assertIsNone(expand_short_quote(seed, page, page))
        self.verifier.lookup['SAIA2143::a.pdf::1'] = self.hit['verbatim_text_span'] = page
        self.draft['verbatim_quote'] = seed
        result = self.verify()
        self.assertEqual(result['gate_6a'], 'passed')
        self.assertTrue(result['short_quote_retained'])
        self.assertEqual(result['canonical_verbatim_quote'], seed)
        self.assertEqual(self.nli.calls, 8)

    def test_short_quote_expansion_rejects_missing_seed_and_wrong_chunk(self):
        self.assertIsNone(expand_short_quote('a nonexistent invented phrase', QUOTE, QUOTE))
        self.assertIsNone(expand_short_quote('handle missing values', QUOTE, 'A completely different chunk'))
        self.assertIsNone(expand_short_quote('missing', QUOTE, QUOTE))

    def test_short_quote_expansion_uses_matching_chunk_for_duplicate_seed(self):
        first = 'People discuss handling missing values for unrelated business reasons.'
        second = 'Students implement handling missing values by fitting a mean imputer.'
        quote = expand_short_quote('handling missing values', first + '\n' + second, second)
        self.assertEqual(quote, second)

    def test_routed_and_pooled_budget_reach_openai_backend(self):
        service = LLMJudgementService(AuditConfig(backend='openai_compat'))
        single = {'c': 'Not Found'}
        pooled = {level: ['Not Found'] for level in LEVELS.values()}
        requests = []
        def reply(request, **kwargs):
            requests.append(json.loads(request.data))
            value = single if len(requests) == 1 else pooled
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(value)}}],
                'usage': {'prompt_tokens': 30, 'completion_tokens': 10}}).encode())
        skill = {'skill_id': 'S01', 'skill_name': 'Cleaning', 'retrieval_query': 'clean data'}
        with patch('src.llm_judgement_service.urlopen', side_effect=reply):
            _, routed = service.judge('SAIA2143', skill, [self.hit], 'Taught')
            _, baseline = service.judge('SAIA2143', skill, [self.hit])
        self.assertEqual([r['max_tokens'] for r in requests], [128, 140])
        self.assertEqual(routed['max_new_tokens'], 128)
        self.assertEqual(baseline['max_new_tokens'], 140)
        self.assertFalse(baseline['decoding_budget_reached'])

    def test_short_quote_expansion_handles_wrapped_sentences(self):
        page = 'Students handle missing values\nby applying a mean imputation procedure to numeric columns.'
        quote = expand_short_quote('handle missing values', page, page)
        self.assertEqual(quote, page)

    def test_short_quote_parent_numbered_item_stops_before_next_task(self):
        page = ('2. Build a framework that involves: o Select a public dataset. '
                'o Perform data cleaning and EDA. o Evaluate the model. '
                '3. Prepare a project report with references.')
        expanded = expand_short_quote('Perform data cleaning and EDA.', page, page)
        self.assertIn('Build a framework', expanded)
        self.assertNotIn('3. Prepare', expanded)
        self.assertIn(expanded, page)

    def test_json_completion_recognizes_escaped_braces_and_incomplete_strings(self):
        self.assertFalse(json_object_complete('{"c":"Supported","q":"not closed'))
        self.assertTrue(json_object_complete(json.dumps({'c':'Supported','q':'braces } { and "quotes"'})))
        self.assertTrue(json_object_complete(json.dumps({'CLO':['Not Found'], 'Taught':['Not Found'], 'Assessed':['Not Found']})))
        self.assertFalse(json_object_complete('{} trailing commentary'))
        self.assertFalse(json_object_complete('{} {}'))
        self.assertFalse(json_object_complete('[]'))

    def test_gate_6a_resolves_quote_on_candidate_two_or_three(self):
        original = {**self.hit, 'verbatim_text_span': 'Original page contains unrelated curriculum material.'}
        for rank in (2, 3):
            with self.subTest(rank=rank):
                hits = [copy.deepcopy(original) for _ in range(rank)]
                peer = {**self.hit, 'doc_id': 'peer.pdf', 'pdf_page_no': 7,
                        'slide_or_section_title': 'Verified peer methods'}
                hits[-1] = peer
                verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1': original['verbatim_text_span'],
                                                'SAIA2143::peer.pdf::7': QUOTE}, self.nli)
                draft = copy.deepcopy(self.draft)
                result = verifier.verify('SAIA2143', 'Taught', self.skill, draft, hits)
                self.assertEqual(result['final_classification'], 'Supported')
                self.assertTrue(result['citation_resolved'])
                self.assertEqual(result['resolved_candidate_rank'], rank)
                self.assertEqual(result['verified_citation']['doc_id'], 'peer.pdf')
                self.assertEqual(result['verified_citation']['pdf_page_no'], 7)
                self.assertEqual(draft, self.draft)
                self.assertTrue(any('Verified peer methods' in p for p in self.nli.premises))
                self.assertTrue(any(t['premise_variant']=='title_and_quote' for t in result['atomic_nli_scores']))

    def test_gate_6a_never_resolves_across_course_level_or_outside_top_three(self):
        original = {**self.hit, 'verbatim_text_span': 'An unrelated page contains no matching quotation.'}
        for replacement in ({'course_code':'SAIA2113'}, {'evidence_level':'Assessed'}):
            with self.subTest(replacement=replacement):
                peer = {**self.hit, 'doc_id':'peer.pdf', **replacement}
                verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1':original['verbatim_text_span'],
                                                f"{peer['course_code']}::peer.pdf::1":QUOTE}, self.nli)
                result = verifier.verify('SAIA2143','Taught',self.skill,self.draft,[original,peer])
                self.assertEqual(result['gate_6a'],'rejected')
        peer = {**self.hit,'doc_id':'peer.pdf'}
        verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1':original['verbatim_text_span'],
                                        'SAIA2143::peer.pdf::1':QUOTE},self.nli)
        result = verifier.verify('SAIA2143','Taught',self.skill,self.draft,[original,original,original,peer])
        self.assertEqual(result['gate_6a'],'rejected')
        self.assertEqual(self.nli.calls,0)

    def test_gate_6a_keeps_verified_short_bullets_without_padding(self):
        for seed in ('Train models safely.', 'Apply regularization techniques.',
                     'Use a supervised learning technique.', 'Evaluate models with precision and F1 scores'):
            with self.subTest(seed=seed):
                self.assertTrue(20 <= len(seed) <= 44)
                page = '• ' + seed + '\n• Another unrelated task with additional explanatory detail.'
                hit = {**self.hit, 'verbatim_text_span':page}
                draft = {**self.draft,'verbatim_quote':seed}
                verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1':page},self.nli)
                result = verifier.verify('SAIA2143','Taught',self.skill,draft,[hit])
                self.assertEqual(result['gate_6a'],'passed')
                if result['short_quote_retained']:
                    self.assertEqual(result['canonical_verbatim_quote'],seed)
                else:
                    self.assertIn(seed,result['canonical_verbatim_quote'])
                    self.assertIn(result['canonical_verbatim_quote'],page)

    def test_gate_6a_rejects_paraphrases_and_noncontiguous_quotes(self):
        quote = 'Graphical methods consist of creating charts and graphs to explore data.'
        page = quote.replace('consist of','consists of')
        verifier = CitationSpanVerifier({'SAIA2143::a.pdf::1':page},self.nli)
        result = verifier.verify('SAIA2143','Taught',self.skill,{**self.draft,'verbatim_quote':quote},
                                 [{**self.hit,'verbatim_text_span':page}])
        self.assertEqual(result['gate_6a'],'rejected')
        self.assertEqual(self.nli.calls,0)

    def test_dual_runner_108_cells_and_missing_folder_no_calls(self):
        catalog = {'courses': {c: {'level_availability': {l: not (c=='SAIA2113' and l=='CLO') for l in LEVELS.values()}} for c in COURSES}}
        calls = []
        class RetrieverDouble:
            def __init__(self, *args, **kwargs):
                self.catalog = catalog
                self.manifest = {'mode': 'TEST DOUBLE', 'source_fingerprint': 'fixture'}
            def retrieve(self, course, query, level=None, **kwargs):
                if course=='SAIA2113' and level=='CLO':
                    raise AssertionError('Retrieval called on absent category')
                return []
        class LLMDouble:
            def __init__(self, *args):
                pass
            def judge(self, course, skill, hits, level=None):
                calls.append((course, level))
                decision = {'draft_classification': 'Not Found', 'candidate_rank_selected': None, 'doc_id': None,
                            'pdf_page_no': None, 'verbatim_quote': None, 'rationale': 'Test double'}
                return {l: copy.deepcopy(decision) for l in ([level] if level else LEVELS.values())}, {
                    'latency_ms': 1, 'llm_called': True, 'prompt_tokens': 30, 'completion_tokens': 9, 'tokens_used': 39}
        cuda = types.SimpleNamespace(is_available=lambda: True, mem_get_info=lambda i: (45*1024**3, 45*1024**3), get_device_name=lambda i: 'TEST DOUBLE')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            skills = [{'skill_id': f'S{i:02d}', 'skill_name': 'Test cleaning', 'retrieval_query': 'clean data', 'nli_hypothesis_template': 'clean data'} for i in range(1,13)]
            (output/'course_catalog_manifest.json').write_text(json.dumps(catalog))
            (output/'industry_skills_benchmark.json').write_text(json.dumps(skills))
            (output/'verbatim_lookup_store.json').write_text('{}')
            with patch.dict('sys.modules', {'torch': types.SimpleNamespace(cuda=cuda), 'src.build_indexes': types.SimpleNamespace(Retriever=RetrieverDouble)}), patch('src.citation_span_verifier.NLIVerifier', FakeNLI), patch('src.llm_judgement_service.LLMJudgementService', LLMDouble):
                data = run(output, AuditConfig())
            self.assertEqual(len(data['cells']), 108)
            self.assertEqual(len(data['baseline_batches']), 36)
            self.assertEqual(len(calls), 96+36)
            self.assertNotIn(('SAIA2113', 'CLO'), calls)
            self.assertEqual(sum(r['routed']['final_classification']=='Insufficient Evidence' for r in data['cells']), 12)
            self.assertEqual(sum(r['baseline']['prompt_tokens'] for r in data['cells']), 36*30)
            for name in ('skill_coverage_audit_results.json', 'skill_coverage_audit_report.md', 'routed_vs_baseline_comparison_report.md', 'scope_and_abstention_safety_report.md'):
                self.assertTrue((output/name).exists())


if __name__ == '__main__':
    unittest.main()
