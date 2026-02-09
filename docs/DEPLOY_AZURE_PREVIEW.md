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
export SYNC_INTERVAL_SECONDS=3600
```

说明
- `AZ_ACR_NAME` 需要全局唯一。若默认名称冲突，请改成带前缀后缀的唯一值。
- 脚本会为 API 设置 `ALLOWED_ORIGINS=https://<web-domain>`，并在构建 Web 镜像时注入 `NEXT_PUBLIC_API_BASE=https://<api-domain>`。
- 首次部署后，worker 会按 `SYNC_*` 参数周期拉取试验数据。

上线后验收
```bash
curl -fsS https://<api-domain>/health
curl -fsS https://<api-domain>/readyz
curl -fsS "https://<api-domain>/api/trials?page=1&page_size=5"
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
