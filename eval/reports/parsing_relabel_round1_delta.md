# Parsing Relabel Round1 Delta Report

## Summary

- final_overlap_trials_applied: 60
- final_changed_trials: 37
- release_overlap_trials_applied: 63
- blind_overlap_trials_applied: 57

### Release

| Metric | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| precision | 0.5052 | 0.7500 | +0.2448 |
| recall | 0.5826 | 0.3137 | -0.2689 |
| f1 | 0.5411 | 0.4424 | -0.0987 |
| hallucination_rate | 0.0024 | 0.0024 | +0.0000 |

| Count | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| tp | 194 | 288 | +94 |
| fp | 190 | 96 | -94 |
| fn | 139 | 630 | +491 |

| Dataset | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| trial_count | 100 | 100 | +0 |
| gold_rule_count | 358 | 920 | +562 |
| unique_fields | 7 | 8 | +1 |

| Field | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| age | 44 | 65 | +21 |
| condition | 216 | 344 | +128 |
| history | 19 | 70 | +51 |
| lab | 1 | 130 | +129 |
| medication | 2 | 86 | +84 |
| other | 0 | 45 | +45 |
| procedure | 2 | 110 | +108 |
| sex | 74 | 70 | -4 |

### Blind

| Metric | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| precision | 0.5166 | 0.8477 | +0.3311 |
| recall | 0.2251 | 0.1508 | -0.0743 |
| f1 | 0.3136 | 0.2560 | -0.0576 |
| hallucination_rate | 0.0000 | 0.0000 | +0.0000 |

| Count | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| tp | 156 | 256 | +100 |
| fp | 146 | 46 | -100 |
| fn | 537 | 1442 | +905 |

| Dataset | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| trial_count | 60 | 60 | +0 |
| gold_rule_count | 699 | 1698 | +999 |
| unique_fields | 8 | 8 | +0 |

| Field | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| age | 27 | 43 | +16 |
| condition | 268 | 456 | +188 |
| history | 125 | 190 | +65 |
| lab | 39 | 161 | +122 |
| medication | 91 | 287 | +196 |
| other | 54 | 106 | +52 |
| procedure | 55 | 394 | +339 |
| sex | 40 | 61 | +21 |

## Gate Check

- release_f1_delta: -0.0987
- blind_f1_delta: -0.0576
- result: FAIL (both release/blind F1 must improve)

