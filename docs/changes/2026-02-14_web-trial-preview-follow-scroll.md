# 2026-02-14 Web: Trial Preview 跟随滚动（Mobile Dock + Drawer）

## Why
- `/matches/<id>` 在窄窗口/小屏下会变成单列布局，Trial preview 会被挤到结果列表底部，滚动对比时需要来回滑动，影响“工作台”体验。

## Changes
- 小屏（<= 980px）隐藏右侧分栏预览区，改为底部固定 `Preview Dock` + 可展开的 `Drawer`，实现滚动结果列表时预览入口始终可见。
- `Preview Dock`：展示当前选中结果的 tier、标题（省略号）、fail/unknown 计数，并提供统一入口打开预览。
- `Drawer`：复用现有 `TrialPreviewPanel`（Match snapshot + Key issues），支持遮罩点击关闭、Esc 关闭、Close 按钮关闭；打开时锁定 body 滚动。
- `Show full checklist` 在 mobile 下会关闭 Drawer 并定位/展开左侧对应 trial 的 checklist。
- 新增 E2E：覆盖窄窗口下 Dock/Drawer 行为与“Show full checklist”跳转/展开逻辑。

## Tests
- `npm --prefix "apps/web" run build`
- `npm --prefix "apps/web" run test:e2e`

## Deploy
- 仅 Web：构建并更新 Azure Container App `ca-web-2baacc`。

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision。
