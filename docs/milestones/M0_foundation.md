M0 Foundation

目标
- 建立可运行的开发与部署骨架, 让团队有统一入口

完成定义
- 任何人可以在一台新机器通过一条命令启动 API 与 Web
- /health 与 /readyz 可用且可区分依赖可用性

M0-1 仓库结构与最小文件
目的
- 统一代码结构, 确保所有人知道文件放在哪里
为什么
- 没有统一结构会导致后续目录与导入混乱
输入
- 目录结构方案
步骤
1. 创建目录 `apps/api/app`, `apps/worker`, `apps/web`, `packages/shared`
2. 创建 `apps/api/app/main.py`
3. 创建 `apps/web/pages/index.tsx`
输出
- 目录结构就绪
- `apps/api/app/main.py` 包含 FastAPI app
- `apps/web` 页面可访问
最小实现示例
`apps/api/app/main.py`
```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True, "service": "api"}
```
`apps/web/pages/index.tsx`
```tsx
export default function Home() {
  return <main>Clinical Trial Matching Assistant</main>;
}
```
验收
1. API 启动后访问 /health 返回 200
2. Web 页面显示项目名称

M0-2 docker-compose 与环境变量
目的
- 一键启动所有服务
为什么
- 没有统一启动方式无法协作测试
输入
- 服务清单
步骤
1. 创建 `docker-compose.yml` 包含 api, web, db, redis, worker
2. 创建 `.env.example` 包含 DATABASE_URL, REDIS_URL, CTGOV_BASE_URL
3. 配置端口: api 8000, web 3000, db 5432, redis 6379
输出
- `docker-compose.yml`
- `.env.example`
最小实现示例
`docker-compose.yml`
```yaml
services:
  api:
    build: ./apps/api
    ports: ["8000:8000"]
  web:
    build: ./apps/web
    ports: ["3000:3000"]
  db:
    image: postgres:16
    ports: ["5432:5432"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
  worker:
    build: ./apps/worker
```
`.env.example`
```
DATABASE_URL=postgresql://user:pass@db:5432/ctmatch
REDIS_URL=redis://redis:6379/0
CTGOV_BASE_URL=https://clinicaltrials.gov/api/v2
```
验收
1. `docker compose up` 后所有容器健康
2. Web 与 API 可访问

M0-3 健康检查与就绪探针
目的
- 可判断服务是否可用
为什么
- 没有就绪探针无法做部署与监控
输入
- API 基础框架
步骤
1. 实现 /health 返回 {"ok": true, "service": "api"}
2. 实现 /readyz 检查 DB 与 Redis 连接
输出
- `apps/api/app/routes/health.py`
验收
1. 断开 DB 时 /readyz 返回失败
2. DB 正常时 /readyz 返回 ok

M0-4 基础测试与格式
目的
- 建立最低质量门槛
为什么
- 没有最小测试无法保证可持续迭代
输入
- API 与 Web 基础代码
步骤
1. 为 /health 添加 API 单测
2. 为 /readyz 添加连接失败测试
3. 配置 lint 或格式化工具
输出
- 测试文件与配置
验收
1. 测试可通过
2. 代码风格一致
