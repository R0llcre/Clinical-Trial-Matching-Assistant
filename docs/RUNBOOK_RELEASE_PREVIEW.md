# Preview Release Runbook (Azure Container Apps)

This runbook is for the **preview** environment (not production SLA).

## Principles
- Release via **explicit image tags** (easy rollback).
- Prefer **revision rollback** (activate previous revision) over rebuilding.
- Never print or commit secrets (DB URLs, Redis keys, OpenAI keys).

## Components
- Web: Next.js (Container App)
- API: FastAPI (Container App)
- Worker: background sync + parsing (Container App)

## Image Tag Strategy
Use a unique, sortable tag per deployment, for example:
- `YYYYMMDDHHMMSS-m7p4` (timestamp)
- or `git-<shortsha>`

Avoid using `latest` for releases.

## Deploy (Standard)
1. Build and push images to ACR (API/Web/Worker as needed).
2. Update Container Apps to the new image tag.
3. Verify health + smoke flows.

Recommended order:
1. API
2. Worker (if changed)
3. Web

## Rollback (Fast)
Use **Container Apps revisions** to roll back without rebuilding.

1. List revisions:
```bash
az containerapp revision list -g <rg> -n <app> -o table
```

2. Activate the last known-good revision:
```bash
az containerapp revision activate -g <rg> -n <app> --revision <revisionName>
```

3. Confirm traffic is on the expected revision:
```bash
az containerapp show -g <rg> -n <app> --query "properties.latestRevisionName" -o tsv
```

## Smoke Checklist
API:
- `GET /health` returns 200
- `GET /readyz` returns 200
- `GET /api/system/dataset-meta` returns JSON with `trial_total`
- `GET /api/trials?page=1&page_size=5` returns a list

Web:
- `/` loads and can browse trials
- `/match` can run a demo profile end-to-end and open `/matches/<id>`
- Trial detail `/trials/<nct_id>` loads and Parsed criteria filters work

Worker:
- logs show periodic sync without crash loops
- logs include parser source + fallback reasons (when LLM is enabled)

## Secrets & Safety (LLM)
- Inject `OPENAI_API_KEY` into the Worker using **Container Apps secrets** (`secretref:`).
- Do **not** put `OPENAI_API_KEY` into GitHub Actions logs, app logs, PR text, or scripts that echo env.
- Ensure Worker has a strict daily budget and **fallback** to non-LLM parsing on failure.

