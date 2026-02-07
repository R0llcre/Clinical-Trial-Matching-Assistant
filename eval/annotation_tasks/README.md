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

Parsing R1 第三人裁决任务（M5）
- 生成命令:
- `python3 scripts/eval/generate_parsing_adjudication_tasks.py --a eval/annotations/trials_parsing_relabel.round1.annotator_a.jsonl --b eval/annotations/trials_parsing_relabel.round1.annotator_b.jsonl --guideline-version m5-v1 --target-annotator annotator_c --max-trials 120 --output-jsonl eval/annotation_tasks/parsing.relabel.round1.adjudication.annotator_c.jsonl --output-manifest eval/annotation_tasks/manifest.parsing_relabel_round1.adjudication.json`
- 输出:
- `eval/annotation_tasks/parsing.relabel.round1.adjudication.annotator_c.jsonl`
- `eval/annotation_tasks/manifest.parsing_relabel_round1.adjudication.json`

Parsing R2 自复核任务（M5）
- 生成命令:
- `python3 scripts/eval/generate_parsing_self_review_tasks.py --adjudicated eval/annotations/trials_parsing_relabel.round1.adjudicated.annotator_c.jsonl --disagreements eval/annotation_tasks/parsing.relabel.round1.adjudication.annotator_c.jsonl --target-trials 60 --guideline-version m5-v1 --target-annotator annotator_c --output-jsonl eval/annotation_tasks/parsing.relabel.round2.self_review.annotator_c.jsonl --output-manifest eval/annotation_tasks/manifest.parsing_relabel_round2.self_review.json`
- 输出:
- `eval/annotation_tasks/parsing.relabel.round2.self_review.annotator_c.jsonl`
- `eval/annotation_tasks/manifest.parsing_relabel_round2.self_review.json`
