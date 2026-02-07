Parsing Label Contract (v2)

Goal
- Remove label ambiguity in parsing gold data.
- Make parser evaluation stable across release/blind datasets.
- Keep labels aligned with `docs/CRITERIA_SCHEMA.md` and gate metrics.

Scope
- Applies to `labeled_rules` in:
- `eval/data/trials_parsing_release.jsonl`
- `eval/data/trials_parsing_blind.jsonl`

Non-goal
- This document does not define model architecture.
- It defines annotation/output contract only.

Rule Schema (required)
- `type`: `INCLUSION | EXCLUSION`
- `field`: `age | sex | condition | medication | lab | procedure | history | other`
- `operator`: one of contract-allowed operators for the field
- `value`: field/operator specific
- `unit`: optional, field/operator specific
- `evidence_text`: non-empty, copied from source sentence

Field Contract

`age`
- allowed operators: `>=`, `<=`
- value: numeric
- unit: `years` or `null`

`sex`
- allowed operators: `=`
- value: `male | female | all`
- unit: `null`

`condition`
- allowed operators: `IN`, `NOT_IN`
- value: non-empty string phrase
- unit: `null`

`history`
- allowed operators: `IN`, `NO_HISTORY`, `WITHIN_LAST`
- value:
- `IN`/`NO_HISTORY`: non-empty string phrase
- `WITHIN_LAST`: positive integer
- unit:
- `WITHIN_LAST`: `days | weeks | months | years`
- otherwise `null`

`medication`
- allowed operators: `IN`, `NOT_IN`, `WITHIN_LAST`
- value:
- `IN`/`NOT_IN`: non-empty string phrase
- `WITHIN_LAST`: positive integer
- unit:
- `WITHIN_LAST`: `days | weeks | months | years`
- otherwise `null`

`procedure`
- allowed operators: `IN`, `NOT_IN`, `WITHIN_LAST`
- value:
- `IN`/`NOT_IN`: non-empty string phrase
- `WITHIN_LAST`: positive integer
- unit:
- `WITHIN_LAST`: `days | weeks | months | years`
- otherwise `null`

`lab`
- allowed operators: `>=`, `<=`, `IN`
- value:
- `>=`/`<=`: numeric
- `IN`: non-empty string or numeric literal allowed
- unit: optional string or `null`

`other`
- allowed operators: `IN`, `EXISTS`
- value:
- `IN`: non-empty string phrase
- `EXISTS`: `null` preferred
- unit: `null`

Deprecated Patterns (must be migrated out)
- `condition` with operator `=`
- `history` with operator `EXISTS`
- `medication/procedure` with operator `EXISTS`, `=`, `>=`, `<=`
- generic placeholders as value:
- `manual review needed`
- `eligibility criterion`
- `study specific condition`

Normalization Rules
- Numeric strings should be stored as numbers where contract expects numeric.
- Comparator symbols `<`/`>` must be normalized to `<=`/`>=` only when explicitly intended in labels.
- `WITHIN_LAST` must carry both numeric value and normalized unit.
- Keep value concise (entity phrase), not full sentence copies.

Validation
- Run:
- `python3 scripts/eval/validate_parsing_contract.py --trials eval/data/trials_parsing_release.jsonl --trials eval/data/trials_parsing_blind.jsonl`
- Optional strict mode (warnings fail):
- `python3 scripts/eval/validate_parsing_contract.py --trials eval/data/trials_parsing_release.jsonl --trials eval/data/trials_parsing_blind.jsonl --fail-on-warnings`

Acceptance for contract migration completion
- zero schema errors
- zero contract errors
- warning count trending to zero, and no deprecated patterns remaining
