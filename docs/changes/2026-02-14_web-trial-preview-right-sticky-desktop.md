# 2026-02-14 Web: Trial Preview 右侧常驻对比（收紧断点）

## Why
- 当前 Trial preview 在 `<= 980px` 会切换为底部 Dock/Drawer，导致很多桌面小窗口（例如 800–950px）也无法保持“右侧常驻对比”的工作台体验。
- 用户期望：只要页面仍是两列布局，Trial preview 在上下滚动时应始终固定在右侧，便于对比。

## Changes
- 将“切换为 mobile Dock/Drawer”的断点从 `980px` 收紧到 `720px`：
- `> 720px` 保持两列布局，右侧 Trial preview 继续 `sticky` 常驻。
- `<= 720px` 才启用底部 Dock/Drawer，并为左侧列表增加底部 padding 防遮挡。
- 增强 Dock/Drawer 的 resize 行为：从 mobile 宽度 resize 到桌面宽度时自动关闭 Drawer，避免残留遮罩/滚动锁。
- 新增 E2E：覆盖 900px 宽度下右侧预览存在且无 mobile Dock，并在滚动时仍可见。

## Tests
- `npm --prefix "apps/web" run build`
- `npm --prefix "apps/web" run test:e2e`

## Deploy
- 仅 Web：构建并更新 Azure Container App `ca-web-2baacc`。

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision。
