# Why
移动端导航 Drawer 虽然可用，但视觉层次偏“临时组件”：抽屉背景透明、缺少信息结构与图标提示，整体不够像成熟网站的导航体验。

# Changes
- Web：移动端导航 Drawer 增加实体背景（非透明），并加入轻量动效（淡入 + 右侧滑入）。
- Web：导航项改为“图标 + 标题 + 简短说明 + 方向指示”，active 状态更明显。
- E2E：补充断言确保 Drawer 背景不为透明，避免回归为“内容漂浮在遮罩上”的视觉问题。

关键文件：
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/components/layout/MobileNavDrawer.tsx`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/components/layout/MobileNavDrawer.module.css`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/e2e/topbar-mobile.spec.ts`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- Web-only：构建并更新 `ca-web-2baacc` 到新镜像 tag。

# Rollback
- Azure Container Apps：将 `ca-web-2baacc` 回切到上一条可用 revision（本改动不涉及数据迁移）。

