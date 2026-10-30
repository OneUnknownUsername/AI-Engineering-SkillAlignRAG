# Calibration cleanup verification

B200 rerun: 108 routed cells and 36 pooled calls. Routed p90: 912.0 ms. Generation errors: 0. Token-limit truncations: 0. Budgets: 128 routed / 140 pooled tokens.

All 23 accepted citations are canonical lookup-page substrings and pass both gates. Strict physical source levels and all 12 SAIA2113 CLO abstentions were rechecked.

## Short-quote expansion

Schema validation admits 20–39 character seeds to Gate 6A. Gate 6A expands only actual page matches to an enclosing sentence or bullet/paragraph of at least 45 normalized characters, bounded by numbered tasks and bullet boundaries. The expanded span must also belong to the winning chunk. Expansion never bypasses pedagogical or NLI verification.

| Course / skill / level | Original quote | Expanded characters | Final decision |
| --- | --- | --- | --- |
| SAIA2113 / S04 / Assessed | o Number of features (≥ 10 features). | 272 | Not Found |
| SAIA2113 / S08 / Assessed | o Ethical considerations | 166 | Not Found |

## S07 investigation

The prior p44 quote stopped after defining overfitting, before the regularization bullet. Its best score was 0.006359; the old atomic list combined overfitting/underfitting and lacked direct diagnostic and hyperparameter-adjustment wording. The revised four facets separately cover diagnosing overfitting, diagnosing underfitting, applying regularization, and adjusting hyperparameters.

| Diagnostic page | Same-page evidence | Max entailment | Rule | Decision |
| --- | --- | --- | --- | --- |
| 44 | Original p44 quote replay | 0.366699 | domain_aligned_0.20 | Supported |
| 45 | Regularization/hyperparameter adjustment bullet | 0.991699 | entailment_0.40 | Supported |

Full rerun S07/Taught: Supported, entailment 0.997559, Week 1 - INTRODUCTION TO ML.pdf p44.

HF decoding stops after one complete JSON object. Pooled prompts request one 40–60 character quote per supported level (180 quote characters total), avoiding long copied lists under the 140-token budget.

Validation: 76 tests passed; input artifact validation passed; final 108-cell output integrity checks passed.
