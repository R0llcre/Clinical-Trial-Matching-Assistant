# 2026-02-14 Web: Trial Preview Panel v2 (Match Snapshot + Key Issues)

## Why
- 右侧面板的 "Selected trial" 文案容易让人误解为“最终选择/会影响排序”，但实际只是当前结果的预览。
- 预览面板只展示 trial 基本信息，用户仍需要展开左侧卡片或跳转详情页才能理解“为什么是 Potential/Not eligible，以及下一步该补什么数据”。

## Changes
- 升级右侧面板为 "Trial preview"，并增加提示：点击左侧卡片只会切换预览，不会改变排序。
- 新增 "Match snapshot"：展示 tier、score、certainty、以及 pass/unknown/fail/missing 计数。
- 新增 "Key issues / Key checks"：
- 有 FAIL/UNKNOWN 时，优先展示关键问题（Exclusion FAIL → Inclusion FAIL → UNKNOWN）。
- UNKNOWN 规则展示 Missing/Why/What to collect next，并提供 "Update patient"（带 `focus=`）入口。
- 全 PASS 时展示 "All checks passed (based on available data)." 并列出 2–3 条关键 PASS。
- 增加 "Show full checklist"：在右侧面板可一键展开并滚动到左侧对应 trial 的完整 checklist。
- Trial 详情拉取改为 best-effort：即使 `GET /api/trials/{nct_id}` 失败，右侧的 Match snapshot / Key issues 仍可用；详情 tab 内仅显示轻量提示与重试。
- 抽离 match-results 共享类型，减少页面内重复定义。

## Tests
- `npm --prefix "apps/web" run build`
- `npm --prefix "apps/web" run test:e2e`

## Deploy
- 仅 Web：构建并更新 Azure Container App `ca-web-2baacc`。

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision。
