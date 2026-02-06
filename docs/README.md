Docs Index

核心
- PROJECT_OVERVIEW.md 项目目标与边界
- PROJECT_RATIONALE.md 项目存在原因与目标
- ENGINEERING_STANDARDS.md 代码规范与结构

系统与实现
- ARCHITECTURE.md 架构与模块职责
- DATA_MODEL.md 数据模型与持久化策略
- API_SPEC.md API 契约与错误码
- PIPELINES.md 数据同步与解析流程
- CRITERIA_SCHEMA.md 规则结构规范
- MATCHING_LOGIC.md 匹配与评分逻辑
- EVALUATION.md 评估与标注规范
- eval/ANNOTATION_GUIDE.md 双标注执行与一致性验收指南
- eval/ANNOTATION_TEMPLATE.relevance.jsonl 检索相关性标注模板
- eval/ANNOTATION_TEMPLATE.rules.jsonl 规则质量标注模板
- ../eval/annotations/relevance.trials_sample.annotator_a.jsonl M4 检索评估对齐标注（A）
- ../eval/annotations/relevance.trials_sample.annotator_b.jsonl M4 检索评估对齐标注（B）
- ../scripts/eval/run_evaluation.py M4 指标计算脚本
- ../scripts/eval/generate_evaluation_report.py M4 评估报告生成脚本
- ../scripts/eval/generate_retrieval_only_report.py 大样本检索标注报告脚本
- ../scripts/eval/generate_annotation_tasks.py 扩样标注任务生成脚本
- ../scripts/eval/generate_retrieval_v2_tasks.py CTGov API 扩池与分层任务生成脚本
- ../scripts/eval/generate_retrieval_v2_tasks_aact.py AACT 快照扩池与分层任务生成脚本
- ../scripts/eval/generate_retrieval_v2_round3_tasks.py V2 round3 定向高价值任务生成脚本
- ../scripts/eval/generate_relevance_adjudication_tasks.py 检索标签复核任务生成脚本
- ../scripts/eval/apply_relevance_adjudication.py 复核结果回写与 final 标签生成脚本
- ../eval/data/queries.jsonl M4 查询样本集
- ../eval/data/trials_sample.jsonl M4 试验解析样本集
- ../eval/data/patients.jsonl M4 合成患者样本集
- DATA_AND_COMPLIANCE.md 数据与合规边界
- LEADERSHIP_AND_RESPONSIBILITIES.md 负责人职责与下属交付

里程碑
- milestones/M0_foundation.md
- milestones/M1_trial_browse.md
- milestones/M2_profiles_matching.md
- milestones/M3_parsing.md
- milestones/M4_evaluation.md
- milestones/M5_optional_llm.md

备份
- ARCHIVE/PROJECT_OVERVIEW.original.md
