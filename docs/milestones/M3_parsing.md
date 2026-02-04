M3 Parsing

目标
- eligibility 文本结构化并可解释

完成定义
- trial_criteria 表写入结构化规则
- 每条规则包含 evidence_text
- 解析失败不影响系统

M3-1 文本切分
目的
- 分离 inclusion 与 exclusion, 便于规则解析
为什么
- 不分段容易导致规则方向错误
输入
- eligibility_text
步骤
1. 识别包含 "Inclusion" 与 "Exclusion" 的分段
2. 若无分段, 视为单段
3. 句子级拆分并清洗空行
输出
- 预处理模块
验收
1. 输出 inclusion_sentences 与 exclusion_sentences

M3-2 规则解析器 v1
目的
- 解析高频规则, 建立解析下限
为什么
- MVP 需要可解释且稳定的规则
输入
- 预处理后的句子
步骤
1. 年龄规则
2. 性别规则
3. 常见排除关键词
4. 生成 criteria_json
输出
- 解析器模块
验收
1. 每条规则含 evidence_text
2. 解析失败返回 UNKNOWN 规则

M3-3 异步解析任务
目的
- 对新增试验自动解析
为什么
- 解析耗时, 不能阻塞 API
输入
- worker 基础框架
步骤
1. parse_trial(nct_id, parser_version)
2. 成功写入 trial_criteria
3. 失败记录原因
输出
- `apps/worker/tasks.py`
验收
1. 任务运行后 trial_criteria 有数据
2. 失败记录可追溯

M3-4 API 接入解析结果
目的
- API 返回解析后的规则与解释
为什么
- 前端需要展示 checklist
输入
- trial_criteria 表
步骤
1. 在 /api/trials/{nct_id} 中返回 criteria
2. 在 /api/match 中读取 criteria 生成 checklist
输出
- API 输出扩展
验收
1. 前端可展示解析后的条款

M3-5 解析覆盖率统计
目的
- 衡量解析效果
为什么
- 为 M4 评估提供基线
输入
- 解析结果
步骤
1. 统计规则数与失败数
2. 写入 coverage_stats
输出
- coverage_stats 字段
验收
1. coverage_stats 可查询
