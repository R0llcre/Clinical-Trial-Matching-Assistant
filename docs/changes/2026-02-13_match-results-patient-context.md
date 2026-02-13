# M8: Match Results ⇄ Patients Hub 闭环（Patient 摘要 + 链接 + 去长串 ID）

## Why
- 结果页直接展示完整 `patient_profile_id`（长 UUID）会显得像工程日志，不像产品。
- Patients Hub 已上线，但结果页缺少“回到患者”的明确入口，导致用户路径断裂。
- PDF 导出中同样存在长串 ID，影响可读性。

## Changes
- 结果页 `/matches/<id>`：
  - 默认展示 Patient 摘要（如 `Breast Cancer · female · 45y`）+ `Open patient` 入口
  - `Patient ID` 只展示短 ID（前 8 位）
  - 仅在 `?debug=1` 时显示完整 `patient_profile_id` 与 `match_id`
- PDF 导出：
  - 用 `Patient: <summary>` + `Patient ID: <short>` 取代长串 UUID
- 新增工具函数：
  - `apps/web/lib/format/ids.ts`：`shortId()`
- E2E：
  - `match-results.spec.ts` 增加断言：结果页包含 `Open patient` 链接与 Patient 摘要文本

## Tests
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test:e2e`

## Deploy
- 仅更新 Web：构建新镜像 tag 并更新 Azure Container App `ca-web-2baacc`
- smoke：打开 `/matches/<id>`，确认不展示长串 UUID、可跳转 `/patients/<id>`

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision。

