M1 Trial Browse

目标
- 用户可搜索并查看试验详情

完成定义
- 前端可通过 /api/trials 搜索
- 详情页可展示 eligibility_text 与 locations
- 试验数据从外部 API 入库

M1-1 CTgov Client
目的
- 封装外部 API, 提供稳定 search 与 detail
为什么
- 隔离外部变更, 便于测试与降级
输入
- CTgov API base URL
步骤
1. 实现 search_studies(condition, status, page_token)
2. 实现 get_study(nct_id)
3. 处理超时与重试
4. 支持分页 token
输出
- `apps/api/app/services/ctgov_client.py`
验收
1. search_studies 返回结构化列表
2. get_study 返回单试验 raw_json

M1-2 字段映射与入库
目的
- 统一从 raw_json 抽取字段
为什么
- 后续检索依赖结构化字段
输入
- raw_json 示例
步骤
1. 定义字段映射表, 记录 JSON 路径与字段名
2. 抽取 nct_id, title, status, phase, conditions, eligibility_text, locations
3. nct_id 为唯一键 upsert
输出
- `apps/api/app/services/trial_ingestor.py`
- trials 表数据
验收
1. 同一 nct_id 重复同步不重复
2. eligibility_text 正确保存

M1-3 Trials API
目的
- 对前端提供统一查询接口
为什么
- 不直接暴露外部 API
输入
- trials 表
步骤
1. 实现 GET /api/trials 支持分页与过滤
2. 实现 GET /api/trials/{nct_id}
输出
- `apps/api/app/routes/trials.py`
验收
1. 搜索关键词返回列表
2. 详情接口返回 eligibility_text

M1-4 前端试验浏览
目的
- 将搜索结果与详情可视化
输入
- API 接口
步骤
1. Trials Search 页面输入与列表
2. Trial Detail 页面展示详情
3. 列表与详情联动
输出
- `apps/web` 页面与组件
验收
1. 输入关键词返回列表
2. 点击列表项可打开详情

M1-5 同步任务触发
目的
- 让试验数据可定期更新
为什么
- 外部 API 不稳定, 需要本地缓存
输入
- worker 基础框架
步骤
1. 创建 sync_trials 任务
2. 支持 condition 与 status 参数
3. 记录同步日志
输出
- `apps/worker/tasks.py`
验收
1. 任务运行后 trials 有新增或更新
2. 失败时有日志记录
