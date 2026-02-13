# Why
目前 `/patients/<id>/edit?focus=...` 只能滚动到对应 section，但用户仍需要手动新增一行、手动输入缺失字段（尤其是 labs），并且光标不会落在最需要填写的输入框上；这会让 “UNKNOWN → Update patient → 补数据” 的闭环不够顺滑。

# Changes
- Patient edit 页面增强 `focus` 行为（仅首次加载生效，避免覆盖用户输入）：
  - `focus=demographics.age|sex|conditions`：滚动后自动聚焦对应输入框
  - `focus=labs_timeline|history_timeline|medications_timeline|procedures_timeline`：聚焦对应的日期输入
  - `focus=<specific lab name>`（例如 `eosinophils`）：自动预填到第一条空 lab row（否则新增一条），并聚焦 Value 输入
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientEditPage.tsx`
- 修正 timeline 行的输入框 id（避免空格/不稳定 id），以便 focus 行为稳定：
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientEditPage.tsx`
- Playwright：覆盖 “Update patient → edit page 自动预填 + 自动聚焦” 的回归断言：
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/match-results.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- 仅更新 Web（`ca-web-2baacc`）。

# Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切上一条可用 revision。

