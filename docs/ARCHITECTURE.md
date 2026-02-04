Architecture

**架构选择原因**
- 需要稳定的数据同步与缓存, 因此将外部 API 与内部服务解耦
- 解析与匹配有异步与批处理需求, 需要独立 Worker
- 需要可审计与可追溯, 必须落库保存 raw_json 与解析结果

**系统总览**
```text
[Web UI] <-> [FastAPI API]
               |
               | SQL
             [PostgreSQL]
               |
               | Queue/Cache
             [Redis]
               |
            [Worker]
               |
       [ClinicalTrials.gov API]
```

**目录结构建议**
```text
apps/
  api/
    app/
      main.py
      routes/
      services/
      models/
      schemas/
      auth/
  worker/
    tasks.py
    services/
apps/web/
  pages/
  components/
  lib/
packages/shared/
  types/
  clients/
```

**组件职责与输入输出**
Web UI
- 输入: 用户查询、患者画像
- 输出: 试验列表、详情、匹配结果与解释

API Server
- 输入: HTTP 请求
- 输出: JSON 响应
- 关键职责: 鉴权、检索、匹配、读取解析结果

Worker
- 输入: 队列任务
- 输出: 数据库写入或更新
- 关键职责: 试验同步、eligibility 解析、批处理

Database
- 输入: 结构化字段、raw_json、解析结果
- 输出: 试验与匹配查询

Redis
- 输入: 缓存键值、任务消息
- 输出: 缓存结果、任务执行

**数据流**
试验同步
1. Worker 触发 sync_trials
2. CTgov API 拉取试验列表与详情
3. raw_json 写入 trials
4. 抽取字段写入结构化列

解析流程
1. Worker 读取 trials.eligibility_text
2. 切分 inclusion/exclusion
3. 句子级预处理
4. 生成 criteria_json 写入 trial_criteria

匹配流程
1. API 接收 patient_profile 与 filters
2. 候选召回
3. 规则匹配与评分
4. 保存 matches 并返回结果

**非功能性要求**
- 可用性: 解析失败不得中断搜索与浏览
- 可追溯性: 任一匹配结果可追溯来源版本
- 可审计性: 解释必须带证据片段
- 安全性: 不记录敏感输入原文

**失败模式与降级策略**
- 外部 API 失败: 返回缓存或提示稍后重试
- 解析失败: 展示原文并标记无法解析
- LLM 不可用: 自动回退规则解析

**可观测性**
- 指标: 拉取成功率、解析覆盖率、匹配耗时
- 日志: API 429/5xx, 任务失败原因, 解析失败样本
