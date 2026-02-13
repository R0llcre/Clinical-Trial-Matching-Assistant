# Why
目前 Results 页虽然能提示 UNKNOWN 的 “What to collect next”，但用户需要手动回到 Patients 再找入口补数据，闭环不够可执行；同时 Patients 侧缺少可迭代的编辑能力（化验、时间线），导致 UNKNOWN 很难被系统性降低。

# Changes
- Web 新增 Patient Edit 页面：`/patients/[id]/edit`，支持更新基础信息与高级字段（labs / timelines / notes）。
  - 新增：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/pages/patients/[id]/edit.tsx`
  - 新增：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientEditPage.tsx`
  - 新增：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientEditPage.module.css`
- Patients Detail 增加 “Edit patient” 入口。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientDetailPage.tsx`
- Patients API client 增加更新方法（消费 API 的 `PUT /api/patients/{id}`）。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/api.ts`
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/types.ts`
- Match Results：在 UNKNOWN 规则卡内增加 “Update patient” CTA，并携带 `?focus=<missing_field>` 帮助用户直接定位到需要补齐的 section。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.tsx`
- E2E：增加 edit flow 与 update CTA 的回归覆盖，mock server 支持 `PUT /api/patients/<id>`。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/mock-api-server.mjs`
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/match-results.spec.ts`
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/patients.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- 仅更新 Web（`ca-web-2baacc`）。

# Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切上一条可用 revision。

