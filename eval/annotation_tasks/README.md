Annotation Tasks

说明
- 本目录用于存放“待标注任务”与“任务清单”生成结果。
- 当前仓库默认不保留历史任务快照，避免主目录冗余。

历史任务
- M4 期间的历史任务文件已归档到:
- `eval/archive/m4_history/annotation_tasks/`

如何重新生成
- 按 `docs/EVALUATION.md` 中的任务生成命令重新产出即可。

Parsing 高影响复标任务（M5）
- 生成命令:
- `python3 scripts/eval/generate_parsing_relabel_tasks.py --target-trials 120 --output-annotator-a eval/annotation_tasks/parsing.relabel.round1.annotator_a.jsonl --output-annotator-b eval/annotation_tasks/parsing.relabel.round1.annotator_b.jsonl --output-manifest eval/annotation_tasks/manifest.parsing_relabel_round1.json`
- 输出:
- `eval/annotation_tasks/parsing.relabel.round1.annotator_a.jsonl`
- `eval/annotation_tasks/parsing.relabel.round1.annotator_b.jsonl`
- `eval/annotation_tasks/manifest.parsing_relabel_round1.json`
