# 2026-02-14 — Web Match Results Split View + Trial Preview Panel

## Why
- 结果页当前以“卡片列表”为主，想看 trial 的 summary / eligibility / parsed criteria 需要频繁跳转到 `/trials/<nct_id>`，上下文切换成本高。
- 大网站常见的工作台模式（左侧列表 + 右侧预览）更利于快速扫读、对比和决策，也更符合产品化体验预期。

## Changes
- 新增 trial 预览面板（Web-only）：
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/TrialPreviewPanel.tsx`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/TrialPreviewPanel.module.css`
  - 面板通过 `GET /api/trials/{nct_id}` 拉取详情，并提供 `Overview / Eligibility / Parsed` 三个 tab（不展示规则 UUID 等长串 ID）。
- 结果页改为 split view 工作台布局（左列表 + 右预览，移动端自动堆叠）：
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.tsx`
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/features/match-results/MatchResultsPage.module.css`
  - 增加“选中 trial”逻辑与高亮样式，默认选中当前可见列表的第一条。
- Playwright E2E 增加断言，确保预览面板渲染稳定：
  - `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/match-results.spec.ts`

## Tests
```bash
npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build
npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e
```

## Deploy
- 仅部署 Web（更新 `ca-web-2baacc` 镜像 tag）。
- Smoke：
  - 打开 `/matches/<id>`，右侧可看到 Trial Preview（summary 可见，且有 “Open full trial” 链接）。
  - 交互不回归：筛选分组、展开规则细节、导出等功能仍可用。

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision（回滚镜像版本）。

