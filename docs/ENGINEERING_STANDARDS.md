Engineering Standards

目的
- 统一代码规范与文件结构
- 确保工程化、可维护、可扩展
- 让新成员可以无障碍加入

目录结构规范
- apps/api: 后端服务
- apps/web: 前端应用
- apps/worker: 异步任务
- packages/shared: 共享类型与工具
- docs: 文档
- scripts: 脚本与工具

文件命名规范
- Python 文件: snake_case.py
- TypeScript 文件: PascalCase.tsx (组件), camelCase.ts (工具)
- 路由文件: 按资源命名, 例如 trials.py, patients.py
- 目录命名: 全小写, 使用下划线

代码规范
- Python: PEP8, 黑盒格式化工具
- TypeScript: ESLint + Prettier
- 所有公共函数必须有 docstring 或注释
- 每个模块必须包含最小单元测试

接口与文档规范
- 每个 API 必须在 API_SPEC.md 中定义
- 每个数据表必须在 DATA_MODEL.md 中定义
- 任何偏离文档的实现必须先更新文档

版本与迁移
- 数据库迁移使用迁移工具
- 每次迁移必须记录在 migrations 目录

测试规范
- 单元测试: 核心逻辑覆盖
- 集成测试: API 端点覆盖
- 每个里程碑必须有最小测试集

日志与监控规范
- 日志中不得包含患者自由文本
- 每个任务必须记录 task_id
- API 请求必须记录 request_id
