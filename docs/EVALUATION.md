Evaluation

**目标**
- 检索是否能稳定命中相关试验
- 解析是否准确且可解释
- 输出证据是否与原文对齐

**评估数据**
- 检索查询: `eval/data/queries.jsonl`
- 解析样本: `eval/data/trials_sample.jsonl`
- 患者样本: `eval/data/patients.jsonl`

**标签定义**
- `relevance_label=0`: 不相关
- `relevance_label=1`: 部分相关
- `relevance_label=2`: 强相关

**核心指标**
- Top-K HitRate
- nDCG@10
- Parsing Precision/Recall/F1
- Hallucination Rate

**阈值**
- Top-10 HitRate >= 0.70
- Parsing F1 >= 0.80
- Hallucination Rate <= 0.02

**M4 双门禁（必须同时通过）**
- `Smoke Gate`（小样本可运行性）:
- 来源: `eval/reports/m4_evaluation_report.json`
- 门槛: `top_k_hitrate >= 0.70`、`parsing_f1 >= 0.80`、`hallucination_rate <= 0.02`、`annotation_coverage >= 1.0`
- `Release Gate`（大样本统计稳健性）:
- 来源: `eval/reports/retrieval_annotation_report_v2_strict_final.json`
- 门槛: `query_count >= 10`、`total_pairs >= 1500`、`label2_total >= 60`、`queries_with_label2 >= 6`、`min_pairs_per_query >= 120`
- 结论:
- `M4 完成 = Smoke Gate PASS 且 Release Gate PASS`

**标准执行命令**
1. 生成并校验评估数据
- `python3 scripts/eval/generate_eval_data.py --output-dir eval/data`
- `python3 scripts/eval/validate_eval_data.py --data-dir eval/data`

2. 计算烟测指标
- `python3 scripts/eval/run_evaluation.py --queries eval/data/queries.jsonl --trials eval/data/trials_sample.jsonl --relevance eval/annotations/relevance.trials_sample.annotator_a.jsonl --top-k 10 --min-relevance-coverage 1.0`

3. 生成烟测报告
- `python3 scripts/eval/generate_evaluation_report.py --queries eval/data/queries.jsonl --trials eval/data/trials_sample.jsonl --relevance eval/annotations/relevance.trials_sample.annotator_a.jsonl --top-k 10 --min-relevance-coverage 1.0 --output-md eval/reports/m4_evaluation_report.md --output-json eval/reports/m4_evaluation_report.json`

4. 生成最终发布门禁报告
- `python3 scripts/eval/check_m4_release_gate.py --smoke-report eval/reports/m4_evaluation_report.json --retrieval-report eval/reports/retrieval_annotation_report_v2_strict_final.json --output-md eval/reports/m4_release_report.md --output-json eval/reports/m4_release_report.json`

**当前有效报告**
- `eval/reports/m4_evaluation_report.md`
- `eval/reports/m4_release_report.md`
- `eval/reports/retrieval_annotation_report_v2_strict_final.md`
- `eval/reports/retrieval_annotation_report_v2_extended_merged.md`

**历史过程数据**
- 多轮扩样、盲评、复核任务与中间报告已归档到 `eval/archive/m4_history/`
- 当前目录默认不保留历史任务文件，`eval/annotation_tasks/` 按需生成
