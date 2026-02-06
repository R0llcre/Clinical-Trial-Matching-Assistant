M4 Annotation Guide (v1)

Goal
- Make M4 evaluation labels reproducible across annotators.
- Standardize relevance labels (0/1/2) and rule-field annotation format.

Scope
- Retrieval relevance labeling for query-trial pairs.
- Rule-field labeling for parsed eligibility rules.
- This guide does not define model changes; it defines annotation behavior only.

Input Files
- `eval/data/queries.jsonl`
- `eval/data/trials_sample.jsonl`
- `eval/data/patients.jsonl`

Task A: Retrieval Relevance (Required)

Record unit
- One `(query_id, nct_id)` pair per row.

Label set
- `0` not relevant
  - Trial condition/topic is unrelated to query intent.
  - Example: query is diabetes; trial is breast cancer only.
- `1` partially relevant
  - Some overlap exists, but key intent is missing or mismatched.
  - Example: same disease family but different target population or wrong phase/location requirement.
- `2` relevant
  - Trial clearly matches the core condition and intent in the query.

Decision order
1. Determine condition/topic match.
2. Check hard constraints in query (if provided): status, phase, location, age/sex.
3. Assign `0/1/2` based on total fit.

Required output format (JSONL)
- File naming:
  - `eval/annotations/relevance.annotator_a.jsonl`
  - `eval/annotations/relevance.annotator_b.jsonl`
- Each line:
```json
{"query_id":"Q0001","nct_id":"NCT12345678","relevance_label":2,"rationale":"condition and constraints align","annotator_id":"annotator_a","guideline_version":"m4-v1"}
```

Field constraints
- `query_id`: non-empty string
- `nct_id`: non-empty string
- `relevance_label`: integer in `{0,1,2}`
- `rationale`: short reason, plain text
- `annotator_id`: stable annotator identifier
- `guideline_version`: fixed `m4-v1`

Task B: Rule-Field Annotation (Required)

Record unit
- One parsed rule per row from `criteria_json`.

Label set
- `correct`: parsed field/operator/value is consistent with source sentence.
- `partial`: partially correct but missing unit/time-window/details.
- `incorrect`: unsupported by source sentence or contradictory.

Required output format (JSONL)
- File naming:
  - `eval/annotations/rules.annotator_a.jsonl`
  - `eval/annotations/rules.annotator_b.jsonl`
- Each line:
```json
{"nct_id":"NCT12345678","rule_id":"rule-1","field":"age","operator":">=","value":"18","unit":"years","quality_label":"correct","evidence_text":"Participants must be 18 years or older.","annotator_id":"annotator_a","guideline_version":"m4-v1"}
```

Field constraints
- `quality_label` in `{correct,partial,incorrect}`
- `evidence_text` must be copied from trial eligibility sentence

Two-Annotator Workflow
1. Pilot set
  - Both annotators label the same 30 query-trial pairs independently.
2. Agreement check
  - Run:
  - `python3 scripts/eval/compute_relevance_agreement.py --a eval/annotations/relevance.annotator_a.jsonl --b eval/annotations/relevance.annotator_b.jsonl`
3. Threshold gate
  - `percent_agreement >= 0.80`
  - `cohen_kappa >= 0.75`
4. Adjudication (if gate fails)
  - Review mismatches only; update guide examples.
  - Re-run pilot on another 20 pairs.
5. Full annotation
  - Annotate full dataset with the same format/version.

Quality Rules
- Do not infer facts not present in source text.
- If uncertain, choose lower confidence label (`1` for relevance, `partial` for rule quality).
- Keep rationale concise and evidence-based.
- Do not edit IDs from source files.

Acceptance for M4-2
- Guide file exists and is versioned.
- Label definitions and output schemas are explicit.
- Two annotators can run the same process and pass agreement gate.
