Azure Preview Deployment (East US)

目标
- 先把当前系统部署到 Azure 预览环境，再持续迭代。
- 默认区域: `eastus`（Azure Global / 美国）。

部署拓扑
- `ca-web-preview`: Next.js 前端（公网）
- `ca-api-preview`: FastAPI 后端（公网）
- `ca-worker-preview`: 同步与解析后台任务
- `pg-ctmatch-preview`: PostgreSQL Flexible Server
- `redis-ctmatch-preview`: Azure Cache for Redis
- `acrctmatchpreview`: Azure Container Registry

前置条件
- 已安装并登录 Azure CLI:
- `az login`
- `az account set --subscription <your-subscription-id>`
- 本地已安装 `openssl`。

一键脚本
- 脚本路径: `/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant/scripts/deploy/azure_preview.sh`
- 默认就会使用 `eastus`。

执行
```bash
cd "/Users/shenkairan/.codex/worktrees/f936/Clinical Trial Matching Assistant"
scripts/deploy/azure_preview.sh
```

可选环境变量（覆盖默认值）
```bash
export AZ_LOCATION=eastus
export AZ_RESOURCE_GROUP=rg-ctmatch-preview
export AZ_ACR_NAME=<globally-unique-acr-name>
export AZ_CONTAINERAPPS_ENV=cae-ctmatch-preview
export AZ_API_APP=ca-api-preview
export AZ_WEB_APP=ca-web-preview
export AZ_WORKER_APP=ca-worker-preview
export AZ_PG_SERVER=pg-ctmatch-preview
export AZ_PG_DB=ctmatch
export AZ_PG_USER=ctmatchadmin
export AZ_PG_PASSWORD='<strong-password>'
export AZ_REDIS_NAME=redis-ctmatch-preview
export IMAGE_TAG=$(date +%Y%m%d%H%M%S)
export SYNC_CONDITION=cancer
export SYNC_PAGE_LIMIT=1
export SYNC_PAGE_SIZE=200
export SYNC_INTERVAL_SECONDS=3600
export SYNC_PROGRESSIVE_BACKFILL=0
export SYNC_REFRESH_PAGES=1
export SYNC_TARGET_TRIAL_TOTAL=0
export SYNC_PARSER_VERSION=llm_v1
export LLM_PARSER_ENABLED=1
export OPENAI_MODEL=gpt-4o-mini
export LLM_DAILY_TOKEN_BUDGET=200000
```

说明
- `AZ_ACR_NAME` 需要全局唯一。若默认名称冲突，请改成带前缀后缀的唯一值。
- 脚本会为 API 设置 `ALLOWED_ORIGINS=https://<web-domain>`，并在构建 Web 镜像时注入 `NEXT_PUBLIC_API_BASE=https://<api-domain>`。
- 首次部署后，worker 会按 `SYNC_*` 参数周期拉取试验数据。
- 启用 LLM 解析时，建议把 `OPENAI_API_KEY` 配成 Container Apps secret，并通过 `secretref:` 注入 worker。
- 当 LLM 不可用或预算命中时，worker 会自动回退到 `rule_v1`，同步不中断。

数据扩容（可选）
- 默认同步逻辑会从第一页开始抓取 `SYNC_PAGE_LIMIT` 页，长期可能反复更新同一批 studies，新增插入逐步变少。
- 如需把 trials 数据量扩容到更大的覆盖面，可启用渐进式回填：
  - `SYNC_PROGRESSIVE_BACKFILL=1`
  - `SYNC_REFRESH_PAGES=1`（每轮先刷新首页，保证新试验及时入库）
  - `SYNC_TARGET_TRIAL_TOTAL=50000`（示例：上限 50k，避免 DB 无上限增长）
- 达到上限后，worker 会自动只跑 refresh，不再继续 backfill。

上线后验收
```bash
curl -fsS https://<api-domain>/health
curl -fsS https://<api-domain>/readyz
curl -fsS "https://<api-domain>/api/trials?page=1&page_size=5"
curl -fsS https://<api-domain>/api/ops/metrics
curl -fsS https://<api-domain>/api/system/dataset-meta
```

手工功能验收
1. 打开 `https://<web-domain>`，确认试验检索可用。
2. 打开 `https://<web-domain>/match`，提交匹配，确认可跳转 `matches/<id>`。
   - 若使用 `scripts/deploy/azure_preview.sh` 部署，API 会启用预览 Token 发放接口 `GET /api/auth/preview-token`，页面会自动获取并保存 JWT（无需手工生成）。
   - 若该接口未启用，则需要本地生成 JWT：
```bash
python3 scripts/gen_dev_jwt.py
```

回滚
- Container Apps 回滚到上一镜像 tag:
- `az containerapp revision list -n <app> -g <rg> -o table`
- `az containerapp revision activate -n <app> -g <rg> --revision <revision-name>`

成本与安全（预览阶段）
- 当前是预览配置，优先可用性与速度，不是生产 SLA。
- 上线后请尽快完成:
- 限制 PostgreSQL/Redis 访问网络策略
- JWT 密钥轮换
- ACR 凭证与容器密钥改用 Managed Identity

可观测性（预览最小闭环）
- API 匹配指标：
```bash
curl -fsS https://<api-domain>/api/ops/metrics | jq
```
- 关键字段：
  - `match.requests_total`
  - `match.success_total`
  - `match.failure_total`
  - `match.avg_duration_ms`
  - `updated_at`
- Worker 同步与解析统计日志（示例）：
```text
sync run completed run_id=<id> processed=120 inserted=30 updated=90 parse_success=28 parse_failed=2 parse_success_rate=0.9333 parser_version=llm_v1 parser_source_breakdown={'llm_v1': 20, 'rule_v1': 8} fallback_reason_breakdown={'OPENAI_API_KEY not set': 8} llm_budget_exceeded_count=0
```

- 按时间窗触发重解析（示例）：
```bash
python3 scripts/ops/reparse_recent_trials.py --parser-version llm_v1 --limit 200 --lookback-hours 72 --condition "heart failure"
```
