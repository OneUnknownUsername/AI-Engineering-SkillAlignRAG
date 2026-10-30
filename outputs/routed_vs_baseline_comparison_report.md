# Routed vs single-pass pooled baseline

Index mode: dense_bm25_hybrid. Hardware: {'device': 'NVIDIA B200 MIG 2g.45gb', 'free_vram_bytes': 47296086016, 'total_vram_bytes': 47513075712}.
Model startup: 28377.6 ms, excluded from warm query timing. No warm-up calls are excluded.
Routed latency includes guard, retrieval, generation and verification. Baseline latency includes pooled retrieval and one three-level generation; retrospective verification is timed separately. Its per-cell latency is the batch latency divided by three, not independently measured level latency.
Baseline classifications below are the unfiltered model decisions. Audit failures do not change them. Model-output errors are explicit review flags in JSON.

| Architecture | Cells | p50 ms / cell | p90 ms / cell | <3000 ms p90 | Prompt tokens | Completion tokens | Local inference API charge / 100 cells | Cloud equivalent / 100 cells |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| routed | 108 | 351.9 | 1013.3 | True | 134840 | 1290 | US$0.00 | Not configured |
| baseline | 108 | 323.9 | 476.1 | True | 42235 | 1203 | US$0.00 | Not configured |

Generation errors requiring manual review: routed 0 cells; pooled 0 batches.

Routed short-quote expansions: 3. Truncated generations: routed 0, pooled 0. Decoding budgets: 128 routed / 140 pooled tokens.

Gate 6A page/rank corrections: routed 1, pooled audit 0. Verified short quotes retained without expansion: routed 0, pooled audit 0.

Measured pooled batch p50 / p90: 971.7 / 1381.4 ms.
Cloud rates are configurable comparison assumptions in USD/million tokens, not a live price quote. Local API charge excludes university compute and electricity costs.

| Architecture | Course | Level | Supported | Not Found | Insufficient Evidence |
| --- | --- | --- | --- | --- | --- |
| routed | SAIA1013 | CLO | 2 | 10 | 0 |
| routed | SAIA1013 | Taught | 3 | 9 | 0 |
| routed | SAIA1013 | Assessed | 1 | 11 | 0 |
| routed | SAIA2113 | CLO | 0 | 0 | 12 |
| routed | SAIA2113 | Taught | 10 | 2 | 0 |
| routed | SAIA2113 | Assessed | 1 | 11 | 0 |
| routed | SAIA2143 | CLO | 2 | 10 | 0 |
| routed | SAIA2143 | Taught | 3 | 9 | 0 |
| routed | SAIA2143 | Assessed | 3 | 9 | 0 |
| baseline | SAIA1013 | CLO | 0 | 12 | 0 |
| baseline | SAIA1013 | Taught | 7 | 5 | 0 |
| baseline | SAIA1013 | Assessed | 0 | 12 | 0 |
| baseline | SAIA2113 | CLO | 0 | 12 | 0 |
| baseline | SAIA2113 | Taught | 10 | 2 | 0 |
| baseline | SAIA2113 | Assessed | 0 | 12 | 0 |
| baseline | SAIA2143 | CLO | 0 | 12 | 0 |
| baseline | SAIA2143 | Taught | 8 | 4 | 0 |
| baseline | SAIA2143 | Assessed | 2 | 10 | 0 |

| Architecture verification | Gate | Passed | Rejected | Not run |
| --- | --- | --- | --- | --- |
| routed | gate_6a | 29 | 1 | 78 |
| routed | gate_6b | 25 | 4 | 79 |
| baseline_audit | gate_6a | 25 | 2 | 81 |
| baseline_audit | gate_6b | 19 | 6 | 83 |

Baseline unverified citation rate: 8/27 (29.6%); substring/identity/wrong-level rejection rate: 2/27 (7.4%).
SAIA2113 CLO missing-document conflation: 12/12 (100.0%).
Level-dilution miss proxy: 8/25 (32.0%) of verified routed positives were baseline non-support with no matching-level pooled candidate. This measures observed omission, not ground-truth recall or causal attribution.
Baseline retrospective audit time: 752.6 ms.

| Course / skill / level | Routed | Pooled baseline | Observed difference |
| --- | --- | --- | --- |
| SAIA1013 / S02 / Taught | Not Found | Supported | Baseline citation rejected |
| SAIA1013 / S05 / Taught | Not Found | Supported | Different evidence decision; manual review required |
| SAIA1013 / S06 / Taught | Not Found | Supported | Baseline citation rejected |
| SAIA1013 / S08 / CLO | Supported | Not Found | Different evidence decision; manual review required |
| SAIA1013 / S09 / CLO | Supported | Not Found | Different evidence decision; manual review required |
| SAIA1013 / S09 / Assessed | Supported | Not Found | Different evidence decision; manual review required |
| SAIA1013 / S12 / Taught | Not Found | Supported | Different evidence decision; manual review required |
| SAIA2113 / S01 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S02 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S03 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S04 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S05 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S06 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S06 / Assessed | Supported | Not Found | Different evidence decision; manual review required |
| SAIA2113 / S07 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S08 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S09 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S09 / Taught | Supported | Supported | Baseline citation rejected |
| SAIA2113 / S10 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S11 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2113 / S12 / CLO | Insufficient Evidence | Not Found | Missing-document abstention |
| SAIA2143 / S01 / CLO | Supported | Not Found | Different evidence decision; manual review required |
| SAIA2143 / S02 / CLO | Supported | Not Found | Different evidence decision; manual review required |
| SAIA2143 / S02 / Assessed | Supported | Not Found | Different evidence decision; manual review required |
| SAIA2143 / S03 / Assessed | Supported | Not Found | Different evidence decision; manual review required |
| SAIA2143 / S04 / Taught | Not Found | Supported | Baseline citation rejected |
| SAIA2143 / S08 / Taught | Not Found | Supported | Baseline citation rejected |
| SAIA2143 / S08 / Assessed | Not Found | Supported | Baseline citation rejected |
| SAIA2143 / S09 / Taught | Not Found | Supported | Baseline citation rejected |
| SAIA2143 / S10 / Taught | Not Found | Supported | Different evidence decision; manual review required |
| SAIA2143 / S11 / Taught | Not Found | Supported | Baseline citation rejected |
