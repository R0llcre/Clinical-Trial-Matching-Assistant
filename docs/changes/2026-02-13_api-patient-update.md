# M9: API Patient Update (PUT /api/patients/{id})

## Why
- Patients Hub 已支持创建与查看，但无法在不新建记录的情况下补充患者信息（化验/时间线等），导致 UNKNOWN 无法被“修复”。
- 提供 `PUT` 更新能力是实现“补信息 → 重跑匹配 → UNKNOWN 降低”闭环的前置条件。

## Changes
- API 新增：`PUT /api/patients/{id}`（按 token `sub` 隔离）
  - 更新 `profile_json` / `source` / `updated_at`
  - 不存在或非本人数据返回 `PATIENT_NOT_FOUND`（404）
- 文档更新：`docs/API_SPEC.md`
- 测试补齐：`apps/api/tests/test_patients_routes.py`

## Tests
- `pytest -q apps/api/tests`
- `ruff check apps/api`

## Deploy
- 构建并更新 API 镜像到 Azure Container App `ca-api-2baacc`

## Rollback
- Azure Container Apps 将 `ca-api-2baacc` 回切到上一条可用 revision。

