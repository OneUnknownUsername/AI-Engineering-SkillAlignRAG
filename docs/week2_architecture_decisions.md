# V1 Architecture Decisions, Trade-offs, and Traceability — SkillAlignRAG

**Save in:** `docs/week2_architecture_decisions.md`

## 1\. Architecture Needs Derived from Requirements 

| Requirement ID | What does the requirement need? | Architecture Response (V1 Capability Component) |
| :---- | :---- | :---- |
| **FR1 / FR2 / NFR2 / NFR4** | Course evidence must be ingested, updated, and retrieved separately across **CLO** (CI PDFs), **Taught** (lecture slides), and **Assessed** (rubrics) levels with exact page/slide provenance (`course_code`, `evidence_level`, `doc_id`, `page_or_slide_no`, `text_span`) without mixed-file context dilution. | **Multi-Level Course Knowledge Sources** (`CLO`, `Taught`, and `Assessed` stores) paired with **Application Interface & Source-Routing Logic** |
| **FR3 / RAI1** | Every **Supported** judgement must include a verifiable verbatim text span (`100%` presence) and an entailment-verified source citation (`≥ 95%` faithfulness; `≤ 5%` unsupported claims). | **Citation & Span Verification Control** (post-generation deterministic substring check \+ semantic entailment verification) |
| **FR2 / FR4 / RAI2 / RAI3** | Missing course document categories must be flagged deterministically as **Insufficient Evidence** (`100%` abstention accuracy), out-of-scope governance/grading queries must be refused (`≥ 95%`), and confidential exam keys/PII must not leak externally (`0` leaks). | **Scope, Abstention & Privacy Control** |
| **O3 / NFR1 / NFR2 / NFR3** | End-to-end latency (`p90 < 3,000 ms/level`), token expenditure (`< US$0.50 / 100 queries`), per-level F1 (`≥ 0.80`), and citation faithfulness metrics must be systematically recorded across benchmark workloads. | **Evaluation Point** \+ efficient routing path through **Language Model Service** |
| **FR2 / FR3 / FR5** | Academic staff need a clear, side-by-side multi-level audit summary across **CLO**, **Taught**, and **Assessed** evidence for CQI and accreditation review. | **Tabular Skill-Coverage Audit Output** |

---

## 2\. Architecture Decision Record (ADR) 

| Decision | Requirement / Constraint | Alternatives Considered | Selected Option | Trade-off Accepted |
| :---- | :---- | :---- | :---- | :---- |
| **ADR 1: Partition knowledge access into source-routed multi-level stores (`CLO`, `Taught`, `Assessed`)** | **FR1, FR2, NFR2, NFR4:** Must prevent mixed-file context dilution, achieve Macro-F1 ≥ 0.80 across all 3 constructive-alignment levels, and allow incremental single-level updates in \< 5 min. | 1\. Base language model only (no retrieval) 2\. Single pooled knowledge source (conventional single-pass RAG) 3\. Source-routed multi-level knowledge sources (`CLO`, `Taught`, `Assessed`) | **Multi-Level Course Knowledge Sources** with explicit **Source-Routing Logic** | Increased orchestration complexity and 3 separate retrieval calls per full course audit, accepted in exchange for higher per-level recall/F1, strict level provenance, and isolated index updates (\< 5 min). |
| **ADR 2: Add an explicit post-generation Citation & Span Verification Control** | **FR3, RAI1:** Must guarantee 100% verbatim span presence, ≥ 95% citation faithfulness, and ≤ 5% unsupported-claim rate on **Supported** judgements. | 1\. Prompt instructions only (relying on LLM self-citation) 2\. Post-generation LLM-as-a-Judge critique 3\. Explicit **Citation & Span Verification Control** (deterministic substring match \+ semantic entailment check) | **Explicit Citation & Span Verification Control** | Additional verification latency (`NFR1`) and risk of conservative false-negative rejections when evidence is fragmented across slide bullets, accepted to eliminate hallucinated quotes and ensure audit-grade provenance. |
| **ADR 3: Include an explicit pre-retrieval Scope, Abstention & Privacy Control** | **FR2, FR4, RAI2, RAI3:** Must distinguish **Insufficient Evidence** from **Not Found** (100% accuracy), refuse out-of-scope queries (≥ 95%), and prevent external leakage of PII or unpublished exam keys (0 transmissions). | 1\. Prompt-level safety instructions only 2\. Explicit **Scope, Abstention & Privacy Control** checking query intent, payload privacy, and repository file-availability metadata before LLM inference | **Explicit Scope, Abstention & Privacy Control** | Minor pre-processing overhead and potential false refusals on borderline curriculum queries, accepted to guarantee deterministic missing-file abstention (**Insufficient Evidence**) and strict data confidentiality. |
| **ADR 4: Integrate a dedicated Evaluation Point for telemetry and benchmark auditing** | **O3, NFR1, NFR2, NFR3, RAI1, RAI2:** Must measure per-level F1 vs. single-pass RAG baseline, citation faithfulness, p90 latency (\< 3,000 ms/level), and cost (\< US\$0.50 / 100 queries). | 1\. Manual ad-hoc inspection of final outputs 2\. Dedicated **Evaluation Point** capturing structured runtime, token, prediction, and verification logs | **Dedicated Evaluation Point** | Slight logging and storage overhead during execution, accepted to ensure reproducible empirical evaluation against the single-pass RAG baseline. |

---

## 3\. Initial Requirements Traceability Matrix

| Objective | Requirement | Evaluation Criterion | Architecture Element | Later Evidence |
| :---- | :---- | :---- | :---- | :---- |
| **O1** | **FR1, FR5, NFR4** | Provenance Schema Completeness and Tabular Audit Clarity | **Multi-Level Course Knowledge Sources** \+ **Tabular Skill-Coverage Audit Output** | Ingested dataset schema audit showing 100% provenance field completeness (`course_code`, `evidence_level`, `doc_id`, `page_or_slide_no`, `text_span`), incremental update test (\< 5 min), and tabular clarity rubric score. |
| **O2** | **FR3, RAI1** | Source Citation Faithfulness and Verbatim Support | **Citation & Span Verification Control** | Evaluation benchmark audit confirming 100% verbatim span presence, ≥ 95% NLI citation faithfulness, and ≤ 5% unsupported-claim rate on **Supported** outputs. |
| **O1, O2** | **FR2, FR4, RAI2, RAI3** | Missing-Evidence Abstention and Out-of-Scope Refusal | **Scope, Abstention & Privacy Control** \+ **Application Interface & Source-Routing Logic** | Document-omission test results (100% accuracy distinguishing **Insufficient Evidence** from **Not Found**), 20-query safety/scope test (≥ 95% refusal rate), and payload privacy audit (0 leaks). |
| **O3** | **FR2, NFR2** | Multi-Level Skill-Coverage Classification Correctness | **Application Interface & Source-Routing Logic** \+ **Multi-Level Course Knowledge Sources** \+ **Language Model Service** | Comparative benchmark evaluation table reporting per-level Precision, Recall, and Macro-F1 (≥ 0.80) and positive F1 gain over the single-pass RAG baseline. |
| **O3** | **NFR1, NFR3** | Response Latency and Token Cost Efficiency | **Language Model Service** \+ **Evaluation Point** | Benchmark telemetry logs demonstrating p90 latency \< 3,000 ms per evidence-level query (\< 9,000 ms per full 3-level audit) and inference cost \< US\$0.50 per 100 queries. |

---

## 4\. Final V1 Architecture Review Checklist 

- [x] **Does each major component support a requirement or evaluation need?** Yes—every component beyond the base flow maps directly to `FR1–FR5`, `NFR1–NFR4`, or `RAI1–RAI3` (verified in Section 1 and Section 3 above).  
- [x] **Is any important data source, safety control, or evaluation point missing?** No—all three routed course knowledge sources (`CLO`, `Taught`, `Assessed`), both RAI controls (`Scope, Abstention & Privacy Control` and `Citation & Span Verification Control`), and the `Evaluation Point` are explicitly represented.  
- [x] **Have I added any technology or component that is not yet justified?** No—components are labeled strictly by capability/function at V1 without premature lock-in to specific vector databases, LLM weights, or UI frameworks.  
- [x] **Is there a simpler architecture that could still satisfy the requirements?** No—a simpler unrouted single-pass RAG flow without deterministic verification and missing-file checks fails `FR2`, `FR3`, `NFR2`, `NFR4`, `RAI1`, and `RAI2`.