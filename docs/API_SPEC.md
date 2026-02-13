API Spec

**统一约定**
Base URL: /api
认证:
- 敏感接口需携带 Authorization: Bearer <token>
- 当前必填: /api/patients*、/api/match、/api/matches/{id}
响应格式:
- 成功: {"ok": true, "data": {...}, "error": null}
- 失败: {"ok": false, "data": null, "error": {"code": "", "message": "", "details": {}}}
时间字段: ISO 8601
分页参数: page, page_size

**通用错误码**
VALIDATION_ERROR 输入校验失败
UNAUTHORIZED 未登录或 token 无效
FORBIDDEN 权限不足
NOT_FOUND 资源不存在
EXTERNAL_API_ERROR 外部 API 错误
RATE_LIMITED 触发限流
PARSER_FAILED 解析失败
TRIAL_NOT_FOUND 试验不存在
PATIENT_NOT_FOUND 患者画像不存在
MATCH_NOT_FOUND 匹配结果不存在

**Trials**
GET /api/trials
目的: 试验列表检索
输入
- condition 可选, 试验条件关键词
- status 可选, RECRUITING 等
- phase 可选, PHASE1/PHASE2 等
- country, state, city 可选
- page, page_size
校验
- page >= 1
- page_size 1-100
输出
- trials: TrialSummary[]
- total, page, page_size
错误
- VALIDATION_ERROR

GET /api/trials/{nct_id}
目的: 获取单试验详情
输入
- nct_id 必填
输出
- TrialDetail
错误
- TRIAL_NOT_FOUND

**Patients**
POST /api/patients
目的: 创建患者画像
认证: 必填
输入
- profile_json 必填
- source 选填, manual 或 synthea
校验
- demographics.age 必填
- demographics.sex 必填
输出
- PatientProfile
错误
- VALIDATION_ERROR

GET /api/patients
目的: 列表与分页
认证: 必填
输入: page, page_size
输出: patients[], total

GET /api/patients/{id}
目的: 获取患者画像
认证: 必填
错误: PATIENT_NOT_FOUND

**Matching**
POST /api/match
目的: 生成匹配结果
认证: 必填
输入
- patient_profile_id 必填
- filters 可选
  - condition 可选
  - status 可选
  - phase 可选
  - country 可选
  - state 可选
  - city 可选
- top_k 默认 10
校验
- top_k 1-50
- filters.* 若提供必须是字符串
输出
- match_id
- results: MatchResultItem[]
错误
- PATIENT_NOT_FOUND
- PARSER_FAILED

GET /api/matches/{id}
目的: 获取匹配详情
认证: 必填
错误: MATCH_NOT_FOUND

**System**
GET /api/system/dataset-meta
目的: 返回当前数据集规模与解析覆盖概览
输入: 无
输出
- trial_total
- latest_fetched_at
- criteria_coverage
  - trials_with_criteria
  - trials_without_criteria
  - coverage_ratio
- parser_source_breakdown

**Admin**
POST /api/admin/sync
目的: 手动触发试验同步
输入
- condition
- status
- updated_since
输出
- job_id
错误
- FORBIDDEN

POST /api/admin/parse
目的: 触发解析任务
输入
- nct_id 或 batch filters
输出
- job_id
错误
- FORBIDDEN

**数据结构**
TrialSummary
```json
{
  "nct_id": "NCT123",
  "title": "...",
  "status": "RECRUITING",
  "phase": "PHASE2",
  "conditions": ["diabetes"],
  "locations": ["CA, USA"],
  "fetched_at": "2026-02-04T10:00:00Z"
}
```

TrialDetail
```json
{
  "nct_id": "NCT123",
  "title": "...",
  "summary": "...",
  "status": "RECRUITING",
  "phase": "PHASE2",
  "conditions": ["diabetes"],
  "eligibility_text": "...",
  "locations": ["CA, USA"],
  "fetched_at": "2026-02-04T10:00:00Z"
}
```

MatchResultItem
```json
{
  "nct_id": "NCT123",
  "score": 0.82,
  "certainty": 0.64,
  "checklist": {
    "inclusion": [
      {
        "rule_id": "rule-1",
        "verdict": "PASS",
        "evidence": "...",
        "rule_meta": {
          "type": "INCLUSION",
          "field": "age",
          "operator": ">=",
          "value": 18,
          "unit": "years",
          "time_window": null,
          "certainty": "high"
        },
        "evaluation_meta": {
          "missing_field": null,
          "reason": null,
          "reason_code": null,
          "required_action": null
        }
      }
    ],
    "exclusion": [
      {
        "rule_id": "rule-2",
        "verdict": "UNKNOWN",
        "evidence": "...",
        "rule_meta": {
          "type": "EXCLUSION",
          "field": "history",
          "operator": "EXISTS",
          "value": "stroke",
          "unit": null,
          "time_window": null,
          "certainty": "medium"
        },
        "evaluation_meta": {
          "missing_field": "history",
          "reason": "missing required patient field",
          "reason_code": "MISSING_FIELD",
          "required_action": "ADD_HISTORY_TIMELINE"
        }
      }
    ],
    "missing_info": ["HbA1c"]
  }
}
```

Checklist rule object
- `rule_meta` and `evaluation_meta` are optional and may be absent for older data.
- Clients should degrade gracefully when these fields are missing.
- `evaluation_meta.reason_code` (optional): machine-readable reason, e.g. `MISSING_FIELD`, `UNSUPPORTED_OPERATOR`, `NO_EVIDENCE`, `INVALID_RULE_VALUE`.
- `evaluation_meta.required_action` (optional): suggested next data collection step, e.g. `ADD_LAB_VALUE`, `ADD_HISTORY_TIMELINE`, `ADD_PROFILE_NOTES`.

DatasetMeta
```json
{
  "trial_total": 17694,
  "latest_fetched_at": "2026-02-13T01:58:00.000000",
  "criteria_coverage": {
    "trials_with_criteria": 14220,
    "trials_without_criteria": 3474,
    "coverage_ratio": 0.8036
  },
  "parser_source_breakdown": {
    "rule_v1": 13002,
    "llm_v1": 1218
  }
}
```

**示例请求**
```bash
curl -H "Authorization: Bearer <token>" \
  "/api/trials?condition=diabetes&status=RECRUITING&page=1&page_size=20"
```
