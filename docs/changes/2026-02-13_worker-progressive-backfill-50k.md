# Worker Progressive Backfill + 50k Cap (Preview Dataset Expansion)

## Why
Preview 环境当前 trials 数据量会“卡住”，因为 worker 每轮同步都从第一页开始抓取固定页数，长期反复更新同一批 studies，新增插入逐步变少。需要一个渐进式翻页回填机制，在不影响“新数据及时入库”的前提下，持续扩容覆盖面，并为预览环境设置上限避免数据库无上限增长。

## Changes
- Worker 同步新增“渐进式翻页回填（progressive backfill）”能力（默认关闭）：
  - 新增 Postgres 表 `sync_cursors` 记录每个 `(condition, trial_status)` 的 `next_page_token` 游标。
  - 同步流程变为：先刷新前 `SYNC_REFRESH_PAGES` 页，再从游标继续 backfill 旧页面，完成后更新游标。
  - 新增可选数据量上限：`SYNC_TARGET_TRIAL_TOTAL`，达到上限后只做 refresh，不再 backfill。
- 部署脚本与文档补齐 worker 的相关 env 注入与说明。
- 关键文件：
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tasks.py`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/scripts/deploy/azure_preview.sh`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/docs/DEPLOY_AZURE_PREVIEW.md`

## Tests
```bash
pytest -q "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tests"
ruff check "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker"
```

## Deploy
- 仅更新 worker（Azure Container Apps）：`ca-worker-2baacc`
- 建议扩容窗口期配置（非敏感 env）：
  - `SYNC_PROGRESSIVE_BACKFILL=1`
  - `SYNC_REFRESH_PAGES=1`
  - `SYNC_TARGET_TRIAL_TOTAL=50000`
  - `SYNC_INTERVAL_SECONDS=900`
  - `SYNC_PAGE_LIMIT=6`
  - `SYNC_PAGE_SIZE=200`
- 达到上限后可回调为常态同步参数（例如 `SYNC_INTERVAL_SECONDS=3600`, `SYNC_PAGE_LIMIT=3`）。

## Rollback
1. Azure Container Apps 回切上一条可用 revision（worker）。
2. 或将 env 回退为：
   - `SYNC_PROGRESSIVE_BACKFILL=0`
   - `SYNC_TARGET_TRIAL_TOTAL=0`
