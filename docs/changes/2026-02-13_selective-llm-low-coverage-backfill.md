# Selective LLM Parsing For Low-Coverage Trials + Backfill + Dataset Meta Semantics

## Why
- 目前绝大多数 trials 都使用 `rule_v1` 解析，成本低但对复杂/非结构化的 eligibility text 容易产生大量 UNKNOWN/`other` 占位规则，影响匹配可解释性与可执行建议。
- 直接全量切到 LLM 解析会显著增加成本与延迟；更合理的方式是：只对“难解析/低覆盖”的 trials 触发 LLM，并对缺失/低覆盖的存量做小步回填。
- `/api/system/dataset-meta` 的 `parser_source_breakdown` 需要按“实际解析来源”统计，避免 `parser_version=llm_v1` 但最终 fallback 到 rule_v1 时造成误读。

## Changes
- Worker：新增“选择性 LLM”策略（仅当 `rule_v1` 解析低覆盖时触发 `llm_v1` 重解析），并增加每轮/每日硬上限与冷却窗口。
  - 关键文件：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tasks.py`
  - 新增 env（非敏感）：`SYNC_LLM_SELECTIVE`, `SYNC_LLM_SELECTIVE_UNKNOWN_RATIO_THRESHOLD`, `SYNC_LLM_SELECTIVE_UNKNOWN_RULES_MIN`, `SYNC_LLM_SELECTIVE_MAX_LLM_CALLS_PER_RUN`, `SYNC_LLM_SELECTIVE_COOLDOWN_HOURS`
- Worker：新增每轮 backfill（优先补齐 trials_without_criteria，其次补齐低覆盖 rule_v1），默认每轮 20 条。
  - 新增 env（非敏感）：`SYNC_LLM_BACKFILL_ENABLED`, `SYNC_LLM_BACKFILL_LIMIT`
- Worker：修复 LLM 计费记账口径——只要发生过 LLM 调用并返回 usage，就会写入 `llm_usage_logs`（即使最终 quality gate fallback 到 rule_v1）。
  - 关键文件：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tasks.py`
- API：修正 dataset meta 口径：`parser_source_breakdown` 优先读取 `trial_criteria.coverage_stats.parser_source`，缺失时 fallback 到 `parser_version`。
  - 关键文件：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/api/app/routes/system.py`
- 部署脚本与文档：补齐上述 env 注入与说明（不包含任何 secret）。
  - `scripts/deploy/azure_preview.sh`
  - `docs/DEPLOY_AZURE_PREVIEW.md`

## Tests
- Worker:
  - `pytest -q "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker/tests"`
  - `ruff check "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/worker"`
- API:
  - `pytest -q "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/api/tests"`
  - `ruff check "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/api"`

## Deploy
- 仅需部署：Worker + API（Web 不变）
- Worker（非敏感 env 示例）：
  - `SYNC_PARSER_VERSION=rule_v1`
  - `SYNC_LLM_SELECTIVE=1`
  - `SYNC_LLM_SELECTIVE_UNKNOWN_RATIO_THRESHOLD=0.4`
  - `SYNC_LLM_SELECTIVE_UNKNOWN_RULES_MIN=2`
  - `SYNC_LLM_SELECTIVE_MAX_LLM_CALLS_PER_RUN=10`
  - `SYNC_LLM_SELECTIVE_COOLDOWN_HOURS=168`
  - `SYNC_LLM_BACKFILL_ENABLED=1`
  - `SYNC_LLM_BACKFILL_LIMIT=20`
  - `LLM_DAILY_TOKEN_BUDGET=1000000`
- 安全要求：
  - `OPENAI_API_KEY` 必须通过 Container Apps secret + `secretref:` 注入；禁止写入代码/文档/日志。

## Rollback
- Worker：回切上一条可用 revision，并设置：
  - `SYNC_LLM_SELECTIVE=0`
  - `SYNC_LLM_BACKFILL_ENABLED=0`
  - （可选）恢复原 `LLM_DAILY_TOKEN_BUDGET`
- API：回切上一条可用 revision（恢复旧统计口径）。

