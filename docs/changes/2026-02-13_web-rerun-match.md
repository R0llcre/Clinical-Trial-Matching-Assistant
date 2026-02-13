# Why
当前闭环里用户在补完 patient 信息后，仍需要手动回到 Patients / Match 页面重新填写 filters 才能重跑匹配；同时 Patients 的 match history 只能 “View results”，缺少一键复用历史条件重跑的能力，导致迭代成本高、体验不够产品化。

# Changes
- Results 页新增 “Rerun match” 按钮：复用当前 match 的 `patient_profile_id + filters + top_k` 重新调用 `POST /api/match` 并跳转到新结果页。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.tsx`
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.module.css`
- Results 页增加轻量提示：当 `patient.updated_at > match.created_at` 时提示该结果可能已过期，引导 rerun（不阻断）。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.tsx`
- Patients detail 的 match history 增加每条记录的 “Rerun” 按钮（独立 loading，不锁全页），复用该记录的 filters/top_k 重跑。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/patients/PatientDetailPage.tsx`
- Playwright：覆盖 history rerun 会触发一次 `POST /api/match`（不依赖返回不同 match_id，避免 flaky）。
  - 修改：`/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/patients.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- 仅更新 Web（`ca-web-2baacc`）。

# Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切上一条可用 revision。

