# Locked benchmark input

`benchmark_skills.json` contains the locked S01-S12 definitions. Pipeline B uses
the skill names, queries and SFIA labels to retrieve evidence automatically from
Stage B1 records. Input `indsf_provenance` fields are optional and ignored;
`benchmark_provenance.json` is a legacy reference and is no longer read.
Code labels including `ETHICS` and `MELT` are preserved as supplied, not certified
as official SFIA codes.

To replace the benchmark, use this input contract.
Exactly 12 entries are required: A = S01-S03, B = S04-S07,
C = S08-S10, D = S11-S12.

Each entry has this shape (the values shown are placeholders, not an approved skill):

```json
{
  "skill_id": "S01",
  "skill_name": "REPLACE WITH LOCKED NAME",
  "bucket": "A",
  "sfia_codes": ["DATS"],
  "retrieval_query": "Action-focused process description without brand-name stuffing",
  "nli_hypothesis_template": "The course teaches or assesses how to perform the process, including its method and rationale."
}
```

The enclosing file is a JSON list. Use `--extract-only` to generate and inspect B1
records, then `--reuse-extraction --skills-config <path>` to run B1 and B2.
Use `--offline` to require the existing cached sentence-transformers model;
`--model` selects another encoder. No lexical fallback is silently substituted.

B1 records contain `item_id`, `doc_id`, `pdf_page_no`, `role_title`,
`seniority_tier`, `section_type`, `sfia_codes`, `sfia_levels`, and `verbatim_text`.
`base_role_title` links competency-table seniority variants to the active career
profile. `scope: framework` marks appendices without inventing role attribution.
`source_occurrences` retains repeated locations and original table rows. Text is
whitespace/OCR-normalized; table cells and levels are joined into a record, so a
record need not be a contiguous substring of the flattened page. IDs are stable
hashes of document, role, section, normalized text and SFIA levels.

B2 admits entry/associate and mid-level technical items, excludes senior roles,
product management, management duties and framework responsibility definitions,
and retrieves up to `--top-k` records per cluster (default 3). Each generated
`indsf_provenance` entry contains the B1 `item_id`, document, role, page, section,
`matched_source_excerpt`, `match_score` and score components. Scores combine
0.60 semantic cosine, 0.35 IDF keyword cosine (title terms weighted twice), and
0.05 SFIA overlap. Both text components use the best score across the description,
title and comma/ampersand-separated title phrases. Common-tool inventory scores
are multiplied by 0.8 because they provide less evidence of expected practice
than task, skill or competency statements (weight 1.0). Records below `--min-match-score`
(default 0.30) are omitted. A cluster without evidence is labeled `no_match`.

The quality report shows raw/unique counts by role and section, filtering counts
and all twelve mappings. Verification regenerates B1 to detect changed sources,
edited definitions or invalid citations without reloading the semantic model.
Similarity and source verification do not certify full skill coverage.
