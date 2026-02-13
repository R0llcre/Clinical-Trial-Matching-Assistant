# M8: Web Patients Hub

## Why
- 让“患者资料 + 多次匹配 + 历史复查”形成闭环，避免每次 Match 都重复输入同一套信息。
- 把预览体验从单次 Demo 流程升级成更像“大网站门户”的信息架构：列表、创建、详情、历史、可重复操作。

## Changes
- Web 新增 Patients Hub 三个页面：
  - `/patients`：患者列表 + 分页
  - `/patients/new`：新建患者表单
  - `/patients/[id]`：患者详情 + Run match 面板 + Match history 列表
- 新增前端模块：`apps/web/features/patients/*`（API 调用封装、类型、页面组件与样式）
- 全站导航与页脚新增 `Patients` 入口（不暴露 JWT）
- E2E 扩展：
  - mock server 增加 `GET /api/patients`、`GET /api/patients/{id}`、`GET /api/matches`（list）
  - 新增 fixtures 与 `patients.spec.ts` 覆盖 Patients Hub 主路径

## Tests
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test:e2e`

## Deploy
- 仅更新 Web：构建新镜像 tag 并更新 Azure Container App `ca-web-2baacc`
- smoke：`/patients`、`/patients/new`、`/patients/<id>` 可访问；从详情页可 Run match 跳转 `/matches/<id>`

## Rollback
- Azure Container Apps 将 `ca-web-2baacc` 回切到上一条可用 revision。

