Eval Assets

目的
- 保持 `eval` 目录只承载“当前验收可直接使用”的数据与报告。
- 历史中间产物统一放入 `eval/archive/m4_history/`，避免主目录持续膨胀。

当前应优先使用的文件
- 小样本烟测报告:
- `eval/reports/m4_evaluation_report.md`
- `eval/reports/m4_evaluation_report.json`
- M4 最终门禁报告:
- `eval/reports/m4_release_report.md`
- `eval/reports/m4_release_report.json`
- 解析发布报告:
- `eval/reports/parsing_release_report.md`
- `eval/reports/parsing_release_report.json`
- 大样本检索最终报告:
- `eval/reports/retrieval_annotation_report_v2_strict_final.md`
- `eval/reports/retrieval_annotation_report_v2_strict_final.json`
- 扩展样本对照报告:
- `eval/reports/retrieval_annotation_report_v2_extended_merged.md`
- `eval/reports/retrieval_annotation_report_v2_extended_merged.json`

当前应优先使用的标注
- 小样本评估:
- `eval/annotations/relevance.trials_sample.annotator_a.jsonl`
- `eval/annotations/relevance.trials_sample.annotator_b.jsonl`
- 基线检索标注:
- `eval/annotations/relevance.annotator_a.jsonl`
- `eval/annotations/relevance.annotator_b.jsonl`
- 大样本最终集:
- `eval/annotations/relevance.v2.round1_round2_round4.final.jsonl`
- `eval/annotations/relevance.v2.round1_round2_round3b_round4.merged.jsonl`
- 解析发布集:
- `eval/data/trials_parsing_release.jsonl`
- 生成脚本: `scripts/eval/build_parsing_release_dataset.py`（对原始标注做规则质量过滤）

目录说明
- `eval/data/`:
- 固定评估输入（queries/trials/patients）与解析发布样本。
- `eval/annotations/`:
- 当前可复用的标注与最终合并结果。
- `eval/reports/`:
- 当前有效的评估报告。
- `eval/annotation_tasks/`:
- 默认留空，按需由脚本重新生成。
- `eval/archive/m4_history/`:
- M4 扩样与多轮标注过程中的历史中间产物（保留追溯，不参与当前验收）。
