# Why
移动端顶部导航的 Drawer 在部分浏览器/环境下“点开看不到内容”，只出现一条很薄的顶部条。这是因为 Drawer 作为 `position: fixed` 元素被渲染在带 `backdrop-filter` 的 `topbar` 内部时，固定定位可能会被该祖先元素作为 containing block，导致高度被限制在 topbar 的高度范围内。

# Changes
- Web：将移动端导航 Drawer/backdrop 通过 React Portal 渲染到 `document.body`，避免受 `topbar` 的 containing block 影响。
- E2E：新增断言确保 Drawer 高度足够大（避免回归为“只有一条顶部条”）。

关键文件：
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/components/layout/MobileNavDrawer.tsx`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/topbar-mobile.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- Web-only：构建并更新 `ca-web-2baacc` 到新镜像 tag。

# Rollback
- Azure Container Apps：将 `ca-web-2baacc` 回切到上一条可用 revision（本改动不涉及数据迁移）。

