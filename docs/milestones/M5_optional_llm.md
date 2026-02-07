M5 Optional LLM

目标
- 引入 LLM 解析能力，同时保持“可回退、可控成本、可控质量”。

完成定义
- LLM 可用时：支持复杂 eligibility 文本解析（结构化 JSON）。
- LLM 不可用或不安全时：自动降级到 `rule_v1`，系统行为稳定。

M5-1 LLM 解析器
目的
- 处理规则解析器难覆盖的复杂句式与时间窗。

实现
1. 文件：`apps/worker/services/llm_eligibility_parser.py`
2. 调用：OpenAI Chat Completions API。
3. 输出约束：`response_format=json_schema`，并在本地做强校验（字段枚举、operator、evidence、source_span、字段特定约束）。
4. 失败策略：任一异常（禁用、无 key、网络失败、schema 不合法）都抛 `LLMParserError`，由 fallback 逻辑降级到 `parse_criteria_v1`。

关键环境变量
- `LLM_PARSER_ENABLED`：默认 `0`（显式开启才调用 LLM）。
- `OPENAI_API_KEY`：LLM 调用凭证。
- `OPENAI_MODEL`：默认 `gpt-4o-mini`。
- `OPENAI_BASE_URL`：默认 `https://api.openai.com/v1`。
- `OPENAI_TIMEOUT_SECONDS`：默认 `60` 秒。
- `LLM_CRITICAL_FIELDS`：默认 `age,sex,history`，LLM 缺失时由 `rule_v1` 回填。
- `LLM_MIN_FINAL_RULES`：默认 `1`，低于阈值触发回退。
- `LLM_MIN_RULE_COVERAGE_RATIO`：默认 `0.25`，若 `LLM 规则数 / rule_v1 规则数` 低于阈值触发回退。

M5-2 成本控制
目的
- 控制 LLM 每日成本并保证超预算自动降级。

实现
1. 记录表：`llm_usage_logs`（prompt/completion/total tokens，按天聚合）。
2. 预算参数：`LLM_DAILY_TOKEN_BUDGET`（默认 `200000`）。
3. 守门逻辑：`parse_trial(parser_version=\"llm_v1\")` 调用前检查预算；超预算则直接走 `rule_v1`，不触发 LLM 调用。

M5-3 质量门槛
目的
- 防止 LLM 输出幻觉规则进入系统。

实现
1. 规则证据对齐：`evaluate_evidence_alignment`（evidence_text/source_span 对齐源文本）。
2. 阈值参数：`LLM_HALLUCINATION_THRESHOLD`（默认 `0.02`）。
3. 守门逻辑：若 LLM 输出幻觉率超过阈值，自动 fallback 到 `rule_v1`。

验收命令
1. Worker 测试：
- `pytest -q apps/worker/tests`
2. LLM 解析单测：
- `pytest -q apps/worker/tests/test_llm_eligibility_parser.py`
3. Lint：
- `ruff check apps/worker`
