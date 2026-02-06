Evaluation

**评估目标**
- 检索是否找到相关试验
- 解析是否准确且可解释
- 输出是否与原文一致

**数据集设计**
检索相关性数据集
- queries.jsonl
- 字段: query, expected_conditions, expected_location
- 标注: relevance_label 0/1/2

解析评估数据集
- trials_sample.jsonl
- 字段: nct_id, eligibility_text, labeled_rules

合成患者数据集
- patients.jsonl
- 字段: demographics, conditions, labs

**标注规范**
相关性标签
- 0 不相关
- 1 部分相关
- 2 相关

抽取字段
- 年龄, 性别, 疾病, 药物, 实验室指标, 时间窗

**指标**
- Top-K HitRate
- nDCG@10
- 解析 Precision/Recall/F1
- Hallucination rate
- Evidence 对齐率

**阈值建议**
- Top-10 HitRate >= 0.70
- 关键字段 F1 >= 0.80
- Hallucination <= 2%

**评估流程**
1. 生成或采样试验与查询
2. 人工标注相关性与字段
3. 运行评估脚本
4. 输出报告与错误分析

**报告内容**
- 指标结果表
- 错误类型统计
- 失败样本示例

**M4-1 交付文件**
- eval/data/queries.jsonl
- eval/data/trials_sample.jsonl
- eval/data/patients.jsonl

**M4-1 生成与校验命令**
- `python3 scripts/eval/generate_eval_data.py --output-dir eval/data`
- `python3 scripts/eval/validate_eval_data.py --data-dir eval/data`

**M4-3 指标计算命令**
- `python3 scripts/eval/run_evaluation.py --queries eval/data/queries.jsonl --trials eval/data/trials_sample.jsonl --relevance eval/annotations/relevance.trials_sample.annotator_a.jsonl --top-k 10 --min-relevance-coverage 1.0`

**M4-4 报告生成命令**
- `python3 scripts/eval/generate_evaluation_report.py --queries eval/data/queries.jsonl --trials eval/data/trials_sample.jsonl --relevance eval/annotations/relevance.trials_sample.annotator_a.jsonl --top-k 10 --min-relevance-coverage 1.0 --output-md eval/reports/m4_evaluation_report.md --output-json eval/reports/m4_evaluation_report.json`

**大样本检索标注报告（300）**
- `python3 scripts/eval/generate_retrieval_only_report.py --annotator-a eval/annotations/relevance.annotator_a.jsonl --annotator-b eval/annotations/relevance.annotator_b.jsonl --output-md eval/reports/retrieval_annotation_report_300.md --output-json eval/reports/retrieval_annotation_report_300.json`

**扩样任务清单生成（2000 检索 + 200 解析）**
- `python3 scripts/eval/generate_annotation_tasks.py --source eval/annotations/relevance.annotator_a.jsonl --target-retrieval-pairs 2000 --target-parsing-trials 200 --output-retrieval eval/annotation_tasks/relevance.pending.2000.jsonl --output-parsing eval/annotation_tasks/parsing.pending.200.jsonl --output-manifest eval/annotation_tasks/manifest.large_scale.json`
