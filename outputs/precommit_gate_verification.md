# Precommit gate verification

Overall: FAIL

| Gate | Status | Failed checks |
| --- | --- | --- |
| 1 - Output Artifacts & Schema Integrity | PASS | None |
| 2 - CI/CLO OCR & Extraction | PASS | None |
| 3 - Deck Aspect Card Coverage | PASS | None |
| 4 - PII Redaction & Verbatim Parity | PASS | None |
| 5 - Pipeline B Provenance | PASS | None |
| 6 - Retrieval Smoke Test & Repo Hygiene | FAIL | benchmark_fingerprint_current |

Tests: 39 passed in 4.27s.

Detailed counts and evidence: precommit_gate_verification.json.

The retrieval log predates the current benchmark fingerprint. Refresh retrieval and rerun validation before committing.

No pipeline source or existing corpus/report files were changed by this audit.
