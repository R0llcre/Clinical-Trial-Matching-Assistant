# M4 Evaluation Report

- generated_at_utc: 2026-02-06T02:29:43.730519+00:00
- query_count: 10
- trial_count: 8
- relevance_pair_count: 300
- retrieval_evaluated_queries: 4
- retrieval_skipped_queries: 6

## Metric Summary

| Metric | Value | Target | Status |
| --- | ---: | ---: | :---: |
| Top-10 HitRate | 1.0 | 0.7 | PASS |
| nDCG@10 | 1.0 | - | INFO |
| Parsing F1 | 0.4571 | 0.8 | FAIL |
| Hallucination Rate | 0.0 | 0.02 | PASS |

## Error Type Breakdown

| Error Type | Count |
| --- | ---: |
| parse_false_positive:other | 7 |
| parse_false_negative:condition | 6 |
| parse_false_negative:age | 1 |
| parse_false_negative:history | 1 |
| parse_false_negative:lab | 1 |
| parse_false_negative:medication | 1 |
| parse_false_negative:procedure | 1 |
| parse_false_positive:age | 1 |

## Error Samples

1. `parse_false_negative:condition` - {"error_type": "parse_false_negative:condition", "nct_id": "NCT90000001", "rule": {"type": "EXCLUSION", "field": "condition", "operator": "NOT_IN", "value": "active infection", "unit": ""}, "evidence_text": "Active infection"}
2. `parse_false_negative:lab` - {"error_type": "parse_false_negative:lab", "nct_id": "NCT90000001", "rule": {"type": "INCLUSION", "field": "lab", "operator": "<=", "value": "8.5", "unit": "%"}, "evidence_text": "HbA1c <= 8.5%."}
3. `parse_false_positive:other` - {"error_type": "parse_false_positive:other", "nct_id": "NCT90000001", "rule": {"type": "INCLUSION", "field": "other", "operator": "EXISTS", "value": "null", "unit": ""}, "evidence_text": "Exclusion: Active infection or major surgery within the last 3 months."}
4. `parse_false_positive:other` - {"error_type": "parse_false_positive:other", "nct_id": "NCT90000002", "rule": {"type": "INCLUSION", "field": "other", "operator": "EXISTS", "value": "null", "unit": ""}, "evidence_text": "Exclusion Criteria: Pregnancy or breastfeeding."}
5. `parse_false_negative:medication` - {"error_type": "parse_false_negative:medication", "nct_id": "NCT90000003", "rule": {"type": "EXCLUSION", "field": "medication", "operator": "WITHIN_LAST", "value": "30", "unit": "days"}, "evidence_text": "Prior treatment within the last 30 days."}
6. `parse_false_negative:condition` - {"error_type": "parse_false_negative:condition", "nct_id": "NCT90000003", "rule": {"type": "INCLUSION", "field": "condition", "operator": "IN", "value": "heart failure", "unit": ""}, "evidence_text": "Adults with heart failure"}
7. `parse_false_positive:other` - {"error_type": "parse_false_positive:other", "nct_id": "NCT90000003", "rule": {"type": "INCLUSION", "field": "other", "operator": "EXISTS", "value": "null", "unit": ""}, "evidence_text": "Exclusion: Prior treatment within the last 30 days."}
8. `parse_false_negative:condition` - {"error_type": "parse_false_negative:condition", "nct_id": "NCT90000004", "rule": {"type": "INCLUSION", "field": "condition", "operator": "IN", "value": "asthma", "unit": ""}, "evidence_text": "asthma diagnosis"}
9. `parse_false_positive:other` - {"error_type": "parse_false_positive:other", "nct_id": "NCT90000004", "rule": {"type": "INCLUSION", "field": "other", "operator": "EXISTS", "value": "null", "unit": ""}, "evidence_text": "Exclusion: Active infection."}
10. `parse_false_negative:procedure` - {"error_type": "parse_false_negative:procedure", "nct_id": "NCT90000005", "rule": {"type": "EXCLUSION", "field": "procedure", "operator": "WITHIN_LAST", "value": "6", "unit": "months"}, "evidence_text": "major surgery in the last 6 months."}

## Recommendations

1. Improve parser coverage: prioritize rules for missing high-frequency fields shown in parse false negatives.
2. Top observed error type is `parse_false_positive:other`; prioritize it first in M5 parser iteration.
