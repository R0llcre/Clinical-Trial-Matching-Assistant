# M4 Evaluation Report

- generated_at_utc: 2026-02-06T02:50:09.750101+00:00
- query_count: 10
- trial_count: 8
- relevance_pair_count: 80
- retrieval_evaluated_queries: 8
- retrieval_skipped_queries: 2
- retrieval_annotation_coverage: 1.0
- retrieval_fully_annotated_queries: 10

## Metric Summary

| Metric | Value | Target | Status |
| --- | ---: | ---: | :---: |
| Top-10 HitRate | 1.0 | 0.7 | PASS |
| nDCG@10 | 1.0 | - | INFO |
| Parsing F1 | 0.8182 | 0.8 | PASS |
| Hallucination Rate | 0.0 | 0.02 | PASS |

## Error Type Breakdown

| Error Type | Count |
| --- | ---: |
| parse_false_positive:history | 3 |
| parse_false_positive:condition | 2 |
| parse_false_negative:other | 1 |
| parse_false_positive:medication | 1 |
| parse_false_positive:procedure | 1 |

## Error Samples

1. `parse_false_positive:procedure` - {"error_type": "parse_false_positive:procedure", "nct_id": "NCT90000001", "rule": {"type": "EXCLUSION", "field": "procedure", "operator": "WITHIN_LAST", "value": "3", "unit": "months"}, "evidence_text": "Active infection or major surgery within the last 3 months."}
2. `parse_false_positive:history` - {"error_type": "parse_false_positive:history", "nct_id": "NCT90000002", "rule": {"type": "EXCLUSION", "field": "history", "operator": "NO_HISTORY", "value": "breastfeeding", "unit": ""}, "evidence_text": "Pregnancy or breastfeeding."}
3. `parse_false_positive:history` - {"error_type": "parse_false_positive:history", "nct_id": "NCT90000002", "rule": {"type": "EXCLUSION", "field": "history", "operator": "NO_HISTORY", "value": "pregnancy", "unit": ""}, "evidence_text": "Pregnancy or breastfeeding."}
4. `parse_false_positive:condition` - {"error_type": "parse_false_positive:condition", "nct_id": "NCT90000004", "rule": {"type": "EXCLUSION", "field": "condition", "operator": "NOT_IN", "value": "active infection", "unit": ""}, "evidence_text": "Active infection."}
5. `parse_false_positive:medication` - {"error_type": "parse_false_positive:medication", "nct_id": "NCT90000006", "rule": {"type": "EXCLUSION", "field": "medication", "operator": "WITHIN_LAST", "value": "4", "unit": "weeks"}, "evidence_text": "previous treatment in the last 4 weeks."}
6. `parse_false_negative:other` - {"error_type": "parse_false_negative:other", "nct_id": "NCT90000007", "rule": {"type": "INCLUSION", "field": "other", "operator": "EXISTS", "value": "null", "unit": ""}, "evidence_text": "for at least 3 months"}
7. `parse_false_positive:condition` - {"error_type": "parse_false_positive:condition", "nct_id": "NCT90000008", "rule": {"type": "EXCLUSION", "field": "condition", "operator": "NOT_IN", "value": "active infection", "unit": ""}, "evidence_text": "pregnancy, breastfeeding, or active infection."}
8. `parse_false_positive:history` - {"error_type": "parse_false_positive:history", "nct_id": "NCT90000008", "rule": {"type": "EXCLUSION", "field": "history", "operator": "NO_HISTORY", "value": "breastfeeding", "unit": ""}, "evidence_text": "pregnancy, breastfeeding, or active infection."}

## Recommendations

1. Metrics pass configured thresholds; continue with larger holdout validation.
2. Top observed error type is `parse_false_positive:history`; prioritize it first in M5 parser iteration.
