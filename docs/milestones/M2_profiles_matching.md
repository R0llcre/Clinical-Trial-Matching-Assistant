M2 Profiles And Matching

目标
- 完成“患者画像 -> 匹配结果”闭环

完成定义
- 可创建患者画像
- 可生成 Top-K 匹配结果
- 结果包含 PASS, FAIL, UNKNOWN

M2-1 患者画像 CRUD
目的
- 统一患者画像格式, 支持后续匹配
为什么
- 没有统一 schema 无法匹配
输入
- profile_json schema
步骤
1. 定义 profile_json schema
2. 实现 POST /api/patients
3. 实现 GET /api/patients/{id}
4. 实现 GET /api/patients 列表
输出
- patient_profiles 表
验收
1. demographics.age, sex 校验生效
2. 查询返回完整 profile_json

M2-2 匹配 v0
目的
- 实现基础匹配逻辑
为什么
- MVP 必须有可解释匹配
输入
- trials 数据
- patient_profile
步骤
1. 条件召回 trials
2. 年龄与性别硬过滤
3. 输出 PASS/FAIL/UNKNOWN checklist
4. 输出 missing_info
输出
- `apps/api/app/services/matching_engine.py`
验收
1. 返回 Top-K 列表
2. checklist 含 PASS/FAIL/UNKNOWN
3. missing_info 含缺失字段

M2-3 结果持久化
目的
- 让匹配结果可复现
为什么
- 需要保存查询条件与结果
输入
- matches 表结构
步骤
1. 保存 query_json
2. 保存 results_json
输出
- matches 表写入
验收
1. 可以通过 /api/matches/{id} 取回结果

M2-4 前端匹配结果
目的
- 展示匹配结果与解释
输入
- Matching API
步骤
1. Patient Form 页面
2. Match Results 页面
3. checklist 展示
输出
- 前端页面与组件
验收
1. 创建患者后可获取匹配结果
2. 结果展示完整

M2-5 基础权限
目的
- 防止未授权访问患者数据
为什么
- 患者画像属于敏感信息
输入
- Auth 框架
步骤
1. 加入 JWT
2. /api/patients 需授权
输出
- auth 中间件
验收
1. 未登录访问 /api/patients 返回 401
