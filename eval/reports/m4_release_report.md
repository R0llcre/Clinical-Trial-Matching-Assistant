# M4 Release Gate Report

- generated_at_utc: 2026-02-06T23:21:11.412219+00:00
- overall_status: FAIL
- smoke_gate: PASS
- release_gate: FAIL

## Gate Summary

| Gate | Status |
| --- | :---: |
| smoke | PASS |
| release | FAIL |
| generalization | FAIL |

## Check Details

| Check | Source | Actual | Comparator | Target | Status |
| --- | --- | ---: | :---: | ---: | :---: |
| smoke.top10_hitrate | m4_evaluation_report | 1.0 | >= | 0.7 | PASS |
| smoke.parsing_f1 | m4_evaluation_report | 1.0 | >= | 0.8 | PASS |
| smoke.hallucination_rate | m4_evaluation_report | 0.0 | <= | 0.02 | PASS |
| smoke.relevance_coverage | m4_evaluation_report | 1.0 | >= | 1.0 | PASS |
| release.query_count | retrieval_annotation_report_v2_strict_final | 10.0 | >= | 10.0 | PASS |
| release.total_pairs | retrieval_annotation_report_v2_strict_final | 1644.0 | >= | 1500.0 | PASS |
| release.label2_total | retrieval_annotation_report_v2_strict_final | 74.0 | >= | 60.0 | PASS |
| release.queries_with_label2 | retrieval_annotation_report_v2_strict_final | 7.0 | >= | 6.0 | PASS |
| release.min_pairs_per_query | retrieval_annotation_report_v2_strict_final | 140.0 | >= | 120.0 | PASS |
| release.parsing_trial_count | parsing_release_report | 100.0 | >= | 100.0 | PASS |
| release.parsing_rule_count | parsing_release_report | 358.0 | >= | 300.0 | PASS |
| release.parsing_unique_fields | parsing_release_report | 7.0 | >= | 6.0 | PASS |
| release.parsing_f1 | parsing_release_report | 0.51 | >= | 0.8 | FAIL |
| release.parsing_hallucination_rate | parsing_release_report | 0.0029 | <= | 0.02 | PASS |
| generalization.blind_parsing_trial_count | parsing_blind_report | 60.0 | >= | 30.0 | PASS |
| generalization.blind_parsing_f1 | parsing_blind_report | 0.3395 | >= | 0.8 | FAIL |
| generalization.blind_parsing_hallucination_rate | parsing_blind_report | 0.0 | <= | 0.02 | PASS |
| generalization.release_blind_f1_gap | parsing_release_report+parsing_blind_report | 0.1705 | <= | 0.1 | FAIL |

## Release Readiness Interpretation

- M4 evaluation is not release-ready. Fix failed checks before merge.
