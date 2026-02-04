Leadership And Responsibilities

目的
- 明确作为项目负责人需要提供的决策与产出
- 明确每个角色需要交付的成果, 避免责任不清

负责人必须提供的内容
1. 产品边界与风险声明
必须在 docs/PROJECT_OVERVIEW.md 和 UI 中明确

2. 架构与接口契约
必须维护 docs/ARCHITECTURE.md 和 docs/API_SPEC.md

3. 数据模型与版本策略
必须维护 docs/DATA_MODEL.md

4. 里程碑与验收标准
必须维护 docs/EXECUTION_PLAN.md 与 docs/milestones/

5. 质量门槛
必须维护 docs/EVALUATION.md 与阈值

6. 代码规范与工作方式
必须维护 README.md 与开发规范

下属必须交付的内容
Backend
- 按 API_SPEC 实现接口
- 按 DATA_MODEL 完成迁移与索引
- 按 PIPELINES 实现同步与解析任务
- 提供最小可运行示例与测试

ML/NLP
- 按 CRITERIA_SCHEMA 实现解析器
- 提供规则覆盖率与错误分析
- 提供评估脚本与结果

Frontend
- 按 API_SPEC 对接接口
- 实现 Trials, Patients, Match Results 页面
- 确保可用性与错误提示

DevOps
- 实现 docker-compose 与环境变量模板
- 提供部署与监控说明
- 确保 /health 与 /readyz 可用

负责人验收方式
- 每个里程碑验收必须满足 docs/milestones/ 的验收项
- 若验收失败, 负责人有权拒绝合并并要求整改
- 所有偏离文档的实现必须先更新文档
