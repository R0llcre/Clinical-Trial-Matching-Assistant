# Why
- 预览库当前包含大量非开放状态（例如 `COMPLETED/TERMINATED/WITHDRAWN/UNKNOWN`），会稀释“可报名试验”的匹配命中率，也会让数据扩容更快触发上限但收益不大。
- 我们的目标是把预览库聚焦在 **开放状态试验**，并支持 **全站范围**回填（不再受限于少量 condition 列表），让任意病种搜索/匹配更容易命中结果。

# Changes
- Worker: 支持全站同步（Global Open）。
  - 当 `SYNC_CONDITION=__all__`（兼容 `all/*`）时，不再发送 `query.term`，只按 `SYNC_STATUS` 过滤并翻页同步。
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tasks.py`
- Worker: 新增非开放状态清理（Prune）。
  - 新增 `SYNC_PRUNE_TO_STATUS_FILTER=1`：在每轮同步前删除 `status` 不在 `SYNC_STATUS` 集合内的 trials 及其 criteria（先删 `trial_criteria` 再删 `trials`）。
  - 同步统计与日志增加 `pruned_trials/pruned_criteria` 字段。
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tasks.py`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/worker.py`
- Deploy 脚本防漂移：
  - Worker env 注入补齐 `SYNC_STATUS`、`SYNC_PRUNE_TO_STATUS_FILTER`。
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/scripts/deploy/azure_preview.sh`
- 文档更新：
  - 增补 `SYNC_STATUS`（支持逗号分隔）、`SYNC_CONDITION=__all__`、以及 prune 风险与验证方式。
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/docs/DEPLOY_AZURE_PREVIEW.md`

# Tests
- `pytest -q "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tests"`
- `ruff check "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker"`

# Deploy
- 仅部署 Worker（`ca-worker-2baacc`）。
- 推荐预览环境参数（非敏感）：
  - `SYNC_CONDITION=__all__`
  - `SYNC_STATUS=RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION`
  - `SYNC_PRUNE_TO_STATUS_FILTER=1`
  - `SYNC_PROGRESSIVE_BACKFILL=1`
  - `SYNC_REFRESH_PAGES=1`
  - `SYNC_TARGET_TRIAL_TOTAL=100000`
- 注意：不要在任何 PR/日志/终端输出 secret。`OPENAI_API_KEY` 仍必须通过 Container Apps `secretref` 注入。

# Rollback
- 应用层回滚：回切上一条 Worker revision，并设置：
  - `SYNC_PRUNE_TO_STATUS_FILTER=0`
  - `SYNC_CONDITION` 回到原 condition 列表
- 数据层回滚：prune 属于数据删除操作，回滚 revision **不会**恢复已删除 trials；如需恢复只能做 PostgreSQL point-in-time restore。

