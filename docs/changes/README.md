# Change Notes

Every PR must add **one** change note under `docs/changes/`.

## File naming
- `docs/changes/YYYY-MM-DD_<slug>.md`

## Required sections
- `Why`: why this change is needed (problem, goal, user value)
- `Changes`: what changed (include key files/behavior changes)

## Recommended sections
- `Tests`: how it was verified locally/CI
- `Deploy`: what to deploy and how to smoke check
- `Rollback`: how to roll back safely

## Safety
- Do not include secrets (DB/Redis/OpenAI keys, JWTs, connection strings).
- Keep notes factual and user-facing (avoid internal-only jargon).

