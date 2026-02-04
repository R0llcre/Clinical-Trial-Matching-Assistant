Pipelines

**试验同步流程**
目的
- 将外部试验数据同步到本地数据库
- 保留 raw_json 与 data_timestamp 以便可追溯

触发方式
- 管理员手动触发
- 定时任务

步骤
1. 调用 CTgov search 接口获取试验列表
2. 处理分页 token
3. 对每条试验调用 detail 接口
4. 将 raw_json 写入 trials
5. 抽取结构化字段更新 trials
6. 记录 fetched_at 与 data_timestamp

输出
- trials 表更新
- 同步日志与统计

失败处理
- 429/5xx: 指数退避 1s, 2s, 4s, 8s
- 超过重试次数: 记录失败原因

**解析流程**
目的
- 将 eligibility 文本转为结构化规则

步骤
1. 读取 trials.eligibility_text
2. 切分 inclusion/exclusion
3. 句子级拆分与清洗
4. 规则解析输出 criteria_json
5. 写入 trial_criteria

输出
- trial_criteria 表
- coverage_stats

失败处理
- 解析失败写入失败原因
- 不阻塞 API 搜索与详情

**匹配流程**
目的
- 根据患者画像返回 Top-K 试验

步骤
1. 接收 patient_profile 与 filters
2. 候选召回
3. 规则判定与评分
4. 保存 matches

输出
- matches 表
- 返回结果与 checklist

**任务队列**
- sync_trials(condition, status, updated_since)
- parse_trial(nct_id, parser_version)
- parse_trials_batch(filter)

**缓存策略**
- search 结果缓存 6-24 小时
- trial detail 缓存 24-72 小时
- data_timestamp 变化立即失效

**监控指标**
- 拉取成功率
- 解析覆盖率
- 匹配耗时 P95
