# M8 PR-7: Preview Identity + User-Scoped Data + Match History List

## Why
- 需要让预览环境在同一浏览器内具备“稳定身份”，从而可以持续访问自己创建的患者与匹配历史。
- `/api/patients` 与 `/api/matches` 需要按用户隔离，避免跨用户读写造成产品感与合规风险。
- Patients Hub 需要一个轻量的 match 历史列表接口（不返回重的 results_json）。

## Changes
- API:
  - `GET /api/auth/preview-token` 支持可选 query `sub=<uuid>`（合法 UUID 才生效）。
  - `/api/patients*` 与 `/api/matches*` 写入并按 token `sub`（UUID）隔离读取。
  - 新增 `GET /api/matches`：按 `patient_profile_id` 可选过滤 + 分页的 match 列表（不返回 results_json）。
- Web:
  - Session 模块生成并持久化 `ctmatch.preview_sub`，请求 preview token 时带 `sub`，确保同一浏览器稳定身份。
  - 自动迁移旧 preview token（sub 非 UUID）为新 token（触发重新签发）。
- Docs:
  - `docs/API_SPEC.md` 补充 preview token 与 match 列表端点说明，并注明资源隔离规则。

## Tests
- API:
  - `ruff check apps/api`
  - `pytest -q apps/api/tests`
- Web:
  - `npm --prefix apps/web run build`
  - `npm --prefix apps/web run test:e2e`

## Deploy
- 需要同时部署 API + Web（否则旧 web 不带 sub 会被新 API 拒绝）。
- Smoke:
  - Web `/match` 跑一次 demo，能进入 `/matches/<id>`。
  - `GET /api/matches?page=1&page_size=5` 返回列表（需 Bearer token）。

## Rollback
- 回滚 API + Web 到上一个 revision/tag（两者要一起回滚，避免 token 逻辑不一致）。

