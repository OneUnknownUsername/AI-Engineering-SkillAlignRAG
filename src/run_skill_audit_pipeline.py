"""Execute routed 108-cell and single-pass pooled audits; generate inspectable reports."""
from __future__ import annotations
import argparse
import logging
from collections import Counter
from pathlib import Path
from time import perf_counter

from src.common import COURSES, LEVELS, ROOT, fingerprint, md, read_json, write_json
from src.config import AuditConfig
from src.skill_hypotheses import atomic_hypotheses
from src.scope_and_abstention_control import check_scope, missing_document, safety_report


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    position = (len(values)-1)*fraction
    low = int(position)
    return values[low] + (values[min(low+1, len(values)-1)]-values[low])*(position-low)


def citation_cell(result: dict) -> str:
    status = result['final_classification']
    citation = result.get('verified_citation')
    if citation:
        return f"**{status}**<br>{md(citation['doc_id'])}, p{citation['pdf_page_no']}: “{md(citation['verbatim_quote'])}”"
    return status + ('<br>' + md(result['abstention_reason']) if result.get('abstention_reason') else '')


def render_reports(output: Path, data: dict, config: AuditConfig) -> None:
    rows = data['cells']
    lines = ['# Skill coverage audit', '', 'Supported decisions have passed canonical substring, level, pedagogical scope and NLI checks. Not Found means no accepted evidence in the Top-3, not proof that the curriculum lacks the skill.', '']
    for course in COURSES:
        lines += [f'## {course} — {COURSES[course]}', '', '| Skill ID & Name | CLO Status & Verified Citation | Taught Status & Verified Citation | Assessed Status & Verified Citation | NLI & Substring Verification |', '| --- | --- | --- | --- | --- |']
        for skill in data['skills']:
            group = [next(r for r in rows if r['course_code'] == course and r['skill_id'] == skill['skill_id'] and r['level'] == level) for level in LEVELS.values()]
            checks = '<br>'.join(f"{r['level']}: 6A {r['routed'].get('gate_6a', 'not_run')}, 6B {r['routed'].get('gate_6b', 'not_run')}" + (f" (entailment {r['routed']['nli_scores']['entailment']:.3f})" if 'nli_scores' in r['routed'] else '') for r in group)
            lines.append('| ' + ' | '.join([md(skill['skill_id'] + ' ' + skill['skill_name']), *(citation_cell(r['routed']) for r in group), checks]) + ' |')
        lines.append('')
    (output / 'skill_coverage_audit_report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    lines = ['# Routed vs single-pass pooled baseline', '', f"Index mode: {data['index_mode']}. Hardware: {md(data['hardware'])}.",
             f"Model startup: {data['startup_ms']:.1f} ms, excluded from warm query timing. No warm-up calls are excluded.",
             'Routed latency includes guard, retrieval, generation and verification. Baseline latency includes pooled retrieval and one three-level generation; retrospective verification is timed separately. Its per-cell latency is the batch latency divided by three, not independently measured level latency.',
             'Baseline classifications below are the unfiltered model decisions. Audit failures do not change them. Model-output errors are explicit review flags in JSON.', '',
             '| Architecture | Cells | p50 ms / cell | p90 ms / cell | <3000 ms p90 | Prompt tokens | Completion tokens | Local inference API charge / 100 cells | Cloud equivalent / 100 cells |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for architecture in ('routed', 'baseline'):
        metrics = [r[architecture] for r in rows]
        latency = [r['latency_ms'] for r in metrics]
        prompt = sum(r['prompt_tokens'] for r in metrics)
        completion = sum(r['completion_tokens'] for r in metrics)
        equivalent = ((prompt*config.input_usd_per_million + completion*config.output_usd_per_million)/1e6 * 100/len(metrics))
        cost = f'US${equivalent:.4f}; <US$0.50: {equivalent < .50}' if config.input_usd_per_million and config.output_usd_per_million else 'Not configured'
        lines.append(f"| {architecture} | {len(metrics)} | {percentile(latency,.5):.1f} | {percentile(latency,.9):.1f} | {percentile(latency,.9)<3000} | {prompt:g} | {completion:g} | US$0.00 | {cost} |")
    lines += ['', f"Generation errors requiring manual review: routed {sum('generation_error' in r['routed'] for r in rows)} cells; pooled {sum('generation_error' in b for b in data['baseline_batches'])} batches."]
    lines += ['', f"Routed short-quote expansions: {sum(r['routed'].get('short_quote_expanded', False) for r in rows)}. "
              f"Truncated generations: routed {sum(r['routed'].get('generation_truncated', False) for r in rows)}, "
              f"pooled {sum(b.get('generation_truncated', False) for b in data['baseline_batches'])}. "
              f"Decoding budgets: {config.max_new_tokens} routed / {config.pooled_max_new_tokens} pooled tokens."]
    lines += ['', f"Gate 6A page/rank corrections: routed {sum(r['routed'].get('citation_resolved', False) for r in rows)}, "
              f"pooled audit {sum(r['baseline_audit'].get('citation_resolved', False) for r in rows)}. "
              f"Verified short quotes retained without expansion: routed {sum(r['routed'].get('short_quote_retained', False) for r in rows)}, "
              f"pooled audit {sum(r['baseline_audit'].get('short_quote_retained', False) for r in rows)}."]
    batches = data['baseline_batches']
    lines += ['', f"Measured pooled batch p50 / p90: {percentile([b['latency_ms'] for b in batches], .5):.1f} / {percentile([b['latency_ms'] for b in batches], .9):.1f} ms.",
              'Cloud rates are configurable comparison assumptions in USD/million tokens, not a live price quote. Local API charge excludes university compute and electricity costs.', '',
              '| Architecture | Course | Level | Supported | Not Found | Insufficient Evidence |', '| --- | --- | --- | --- | --- | --- |']
    for architecture in ('routed', 'baseline'):
        for course in COURSES:
            for level in LEVELS.values():
                counts = Counter(r[architecture]['final_classification'] for r in rows if r['course_code']==course and r['level']==level)
                lines.append(f"| {architecture} | {course} | {level} | {counts['Supported']} | {counts['Not Found']} | {counts['Insufficient Evidence']} |")
    lines += ['', '| Architecture verification | Gate | Passed | Rejected | Not run |', '| --- | --- | --- | --- | --- |']
    for architecture in ('routed', 'baseline_audit'):
        for gate in ('gate_6a', 'gate_6b'):
            counts = Counter(r[architecture].get(gate, 'not_run') for r in rows)
            lines.append(f"| {architecture} | {gate} | {counts['passed']} | {counts['rejected']} | {counts['not_run']} |")
    supported = [r for r in rows if r['baseline']['final_classification']=='Supported']
    wrong = sum(r['baseline_audit'].get('gate_6a')=='rejected' for r in supported)
    unverified = sum(r['baseline_audit']['final_classification']!='Supported' for r in supported)
    absent = [r for r in rows if r['course_code']=='SAIA2113' and r['level']=='CLO' and not data['availability']['SAIA2113']['CLO']]
    conflation = sum(r['baseline']['final_classification']!='Insufficient Evidence' for r in absent)
    positives = [r for r in rows if r['routed']['final_classification']=='Supported']
    misses = [r for r in positives if r['baseline']['final_classification']!='Supported' and not r['pooled_has_level']]
    def ratio(n, d):
        return f'{n}/{d} ({n/d:.1%})' if d else 'N/A (zero denominator)'
    lines += ['', f"Baseline unverified citation rate: {ratio(unverified,len(supported))}; substring/identity/wrong-level rejection rate: {ratio(wrong,len(supported))}.",
              f"SAIA2113 CLO missing-document conflation: {ratio(conflation,len(absent))}.",
              f"Level-dilution miss proxy: {ratio(len(misses),len(positives))} of verified routed positives were baseline non-support with no matching-level pooled candidate. This measures observed omission, not ground-truth recall or causal attribution.",
              f"Baseline retrospective audit time: {sum(r['baseline_audit']['latency_ms'] for r in rows):.1f} ms.", '',
              '| Course / skill / level | Routed | Pooled baseline | Observed difference |', '| --- | --- | --- | --- |']
    for r in rows:
        a, b = r['routed']['final_classification'], r['baseline']['final_classification']
        if a != b or (b=='Supported' and r['baseline_audit']['final_classification']!='Supported'):
            reason = 'Missing-document abstention' if a=='Insufficient Evidence' else 'Baseline citation rejected' if b=='Supported' and r['baseline_audit']['final_classification']!='Supported' else 'Different evidence decision; manual review required'
            lines.append(f"| {r['course_code']} / {r['skill_id']} / {r['level']} | {a} | {b} | {reason} |")
    (output / 'routed_vs_baseline_comparison_report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def run(output: Path, config: AuditConfig) -> dict:
    # Fail early on absent artifacts, before loading multi-GB weights.
    catalog = read_json(output / 'course_catalog_manifest.json')
    skills = read_json(output / 'industry_skills_benchmark.json')
    if len(skills)!=12 or {s['skill_id'] for s in skills}!={f'S{i:02d}' for i in range(1,13)}:
        raise ValueError('Expected exactly S01–S12')
    for skill in skills:
        atomic_hypotheses(skill)
        if not all(isinstance(skill.get(k), str) and skill[k].strip() for k in ('skill_name', 'retrieval_query', 'nli_hypothesis_template')):
            raise ValueError('Incomplete skill benchmark')
    safety = safety_report(output, catalog)
    from src.build_indexes import Retriever
    from src.citation_span_verifier import CitationSpanVerifier, NLIVerifier
    from src.llm_judgement_service import LLMJudgementService
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('B200/CUDA allocation required for NLI and local inference')
    free, total = torch.cuda.mem_get_info(0)
    hardware = {'device': torch.cuda.get_device_name(0), 'free_vram_bytes': free, 'total_vram_bytes': total}
    logging.info('CUDA startup: %s', hardware)
    startup = perf_counter()
    retriever = Retriever(output, offline=config.offline)
    # NLI first so the LLM placement reserves its actual occupied GPU memory.
    verifier = CitationSpanVerifier(read_json(output / 'verbatim_lookup_store.json'), NLIVerifier(config))
    llm = LLMJudgementService(config)
    data = {'schema_version': 1, 'skills': skills, 'config': vars(config), 'hardware': hardware,
            'index_mode': retriever.manifest['mode'], 'index_source_fingerprint': retriever.manifest['source_fingerprint'],
            'benchmark_fingerprint': fingerprint(skills), 'startup_ms': (perf_counter()-startup)*1000,
            'availability': {c: catalog['courses'][c]['level_availability'] for c in COURSES},
            'safety': safety, 'cells': [], 'baseline_batches': []}
    if retriever.catalog != catalog:
        raise ValueError('Retrieval catalog differs from current course manifest')
    for course in COURSES:
        for skill in sorted(skills, key=lambda s: s['skill_id']):
            query = f"Audit {course} skill {skill['skill_id']} coverage: {skill['skill_name']}"
            if not check_scope(query)['allowed']:
                raise ValueError('Audit request refused by scope control')
            routed = {}
            for level in LEVELS.values():
                start = perf_counter()
                abstention = missing_document(catalog, course, level)
                if abstention:
                    routed[level] = {**abstention, 'candidates': []}
                    continue
                hits = retriever.retrieve(course, skill['retrieval_query'], level, top_k=3)
                drafts, telemetry = llm.judge(course, skill, hits, level)
                routed[level] = {**telemetry, **verifier.verify(course, level, skill, drafts[level], hits),
                                 'draft': drafts[level], 'candidates': hits, 'latency_ms': (perf_counter()-start)*1000}
            start = perf_counter()
            pooled = retriever.retrieve(course, skill['retrieval_query'], top_k=3)
            drafts, telemetry = llm.judge(course, skill, pooled)
            batch_latency = (perf_counter()-start)*1000
            data['baseline_batches'].append({'course_code': course, 'skill_id': skill['skill_id'], **telemetry, 'latency_ms': batch_latency, 'candidates': pooled})
            from src.common import evidence_levels
            for level in LEVELS.values():
                start = perf_counter()
                audit = verifier.verify(course, level, skill, drafts[level], pooled)
                audit['latency_ms'] = (perf_counter()-start)*1000
                baseline = {**telemetry, 'final_classification': drafts[level]['draft_classification'], 'draft': drafts[level],
                            'latency_ms': batch_latency/3,
                            'prompt_tokens': telemetry['prompt_tokens']/3, 'completion_tokens': telemetry['completion_tokens']/3,
                            'tokens_used': telemetry['tokens_used']/3}
                data['cells'].append({'course_code': course, 'skill_id': skill['skill_id'], 'level': level,
                                      'pooled_has_level': any(level in evidence_levels(h) for h in pooled),
                                      'routed': routed[level], 'baseline': baseline, 'baseline_audit': audit})
            logging.info('Completed %s / %s (%d/108 cells)', course, skill['skill_id'], len(data['cells']))
            write_json(output / 'skill_coverage_audit_checkpoint.json', data)
    write_json(output / 'skill_coverage_audit_results.json', data)
    render_reports(output, data, config)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs')
    parser.add_argument('--backend', choices=('hf_local', 'openai_compat'), default='hf_local')
    parser.add_argument('--llm-model', default=AuditConfig.llm_model)
    parser.add_argument('--nli-model', default=AuditConfig.nli_model)
    parser.add_argument('--base-url', default=AuditConfig.base_url)
    parser.add_argument('--cache-path')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--safety-only', action='store_true', help='Run guards without models or indexes')
    parser.add_argument('--input-usd-per-million', type=float, default=0)
    parser.add_argument('--output-usd-per-million', type=float, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.input_usd_per_million < 0 or args.output_usd_per_million < 0:
        parser.error('Cost rates cannot be negative')
    if args.safety_only:
        path = args.output_dir / 'course_catalog_manifest.json'
        safety_report(args.output_dir, read_json(path) if path.exists() else None)
        return
    config = AuditConfig(**{k: v for k, v in vars(args).items() if k not in ('output_dir', 'safety_only')})
    run(args.output_dir, config)


if __name__ == '__main__':
    main()
