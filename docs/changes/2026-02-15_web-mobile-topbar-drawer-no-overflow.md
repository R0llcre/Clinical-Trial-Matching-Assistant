# Why
移动端（例如 390px 宽）顶部导航栏链接横向溢出，导致页面出现横向滚动，“右侧内容被挤出去/看起来坏掉”，影响可用性与产品观感。

# Changes
- Web：移动端顶部导航改为 “Menu + Drawer” 交互，避免横向溢出；桌面端导航保持不变。
- Web：新增 `MobileNavDrawer` 组件用于小屏导航抽屉（支持遮罩点击关闭、Escape 关闭、路由跳转自动关闭、锁定 body 滚动）。
- CSS：在 `<= 720px` 时隐藏桌面 `nav.topnav`，显示 `Menu` 按钮（并确保 Drawer 不产生 `100vw` 溢出）。

关键文件：
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/pages/_app.tsx`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/styles/globals.css`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/components/layout/MobileNavDrawer.tsx`
- `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web/components/layout/MobileNavDrawer.module.css`

# Tests
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run build`
- `npm --prefix "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/apps/web" run test:e2e`

# Deploy
- Web-only：构建并更新 `ca-web-2baacc` 到新镜像 tag。

# Rollback
- Azure Container Apps：将 `ca-web-2baacc` 回切到上一条可用 revision（本改动不涉及数据迁移）。

