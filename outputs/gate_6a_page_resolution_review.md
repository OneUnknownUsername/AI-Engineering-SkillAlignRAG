# Gate 6A short-quote and candidate-page resolution review

Gate 6A accepts verified normalized substrings of at least 20 characters, preferring an enclosing 45-character sentence/bullet where available. The 45-character target never rejects a standalone verified short quote. Page correction is restricted to same-course, same-level candidates among the supplied Top-3; both page and retrieved chunk must contain the quote. Original model outputs stay in JSON, and NLI uses the resolved chunk.

B200 rerun: 108 cells; routed p90 1013.3 ms; 0 routed/pooled generation errors and 0 truncations. Routed page/rank corrections: 1. All 25 accepted routed citations were independently rechecked against canonical lookup pages. 80 tests and input artifact validation passed.

## Actual end-to-end model decisions

| Cell | Before | After | Gate 6A | Gate 6B | Outcome detail |
| --- | --- | --- | --- | --- | --- |
| SAIA2113 / S05 / Assessed | Not Found | Not Found | rejected | not_run | Quote not a canonical page and chunk substring in same-course/level Top-3 |
| SAIA2113 / S06 / Assessed | Not Found | Supported | passed | passed | Page resolved from SAIA 2113 - Machine Learning Project Presentation SEM 1 20252026 (1).pdf p3 to Assignment 1 - ML (12 Nov 2025).pdf p2. Entailment 0.997070. |
| SAIA2113 / S03 / Taught | Not Found | Supported | passed | passed | Entailment 0.998047. |
| SAIA1013 / S08 / Assessed | Not Found | Not Found | passed | rejected | Atomic entailment and domain-alignment thresholds not met Entailment 0.037018. |
| SAIA1013 / S10 / Assessed | Not Found | Not Found | not_run | not_run | LLM returned Not Found; verification was not invoked. |

## Replay and exact-source diagnostic controls

These controls test verification using existing Top-3 candidates; they do not overwrite the end-to-end model decisions above.

| Cell | Diagnostic | Gate 6A | Final diagnostic decision | Entailment |
| --- | --- | --- | --- | --- |
| SAIA1013 / S08 / Assessed | original_replay | rejected | Not Found | not_run |
| SAIA1013 / S08 / Assessed | exact_source_control | passed | Supported | 0.978515625 |
| SAIA1013 / S10 / Assessed | original_replay | passed | Not Found | 0.007232666015625 |
| SAIA1013 / S10 / Assessed | exact_source_control | passed | Not Found | 0.02606201171875 |
| SAIA2113 / S03 / Taught | original_replay | rejected | Not Found | not_run |
| SAIA2113 / S03 / Taught | exact_source_control | passed | Supported | 0.998046875 |
| SAIA2113 / S05 / Assessed | original_replay | rejected | Not Found | not_run |
| SAIA2113 / S05 / Assessed | exact_source_control | passed | Supported | 0.95654296875 |
| SAIA2113 / S06 / Assessed | original_replay | passed | Supported | 0.9970703125 |

## Remaining selection and wording issues

- S05’s emitted composite quote is not contiguous on any candidate page: the task says Apply one supervised learning technique, while the later requirement says Use one supervised learning technique. The exact 37-character Use sentence passes Gate 6A and NLI in the source control. The verifier does not replace words or join disjoint spans.
- The previous S03 quote changed consists to consist; the new model output preserves consists and is Supported.
- The previous S08 quote omitted an interleaved table field label. The source control uses an exact contiguous fairness/privacy/principles excerpt from group-assignment p3 and is Supported. The end-to-end LLM instead selected generic risk-assessment wording from p1, which fails skill-specific NLI.
- The five-risk assessment table on group-assignment p3 explicitly lists Fairness, Privacy, Accountability and Transparency. Its exact excerpt passes Gate 6A for both S08 and S10. S10 remains a semantic/selection limitation: the source-control NLI score is below threshold, and the end-to-end model returned Not Found. No NLI threshold or pedagogical scope gate was relaxed.
