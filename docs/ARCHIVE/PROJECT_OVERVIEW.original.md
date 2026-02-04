可以，我把我说的 **Clinical Trial Matching Assistant（临床试验匹配助手）**按“你真的要做出来并能放在作品集/申请材料里”的标准，给你一个**从动机→数据→AI 方法→系统架构→评估→交付物→时间表**的完整介绍。

> 重要声明（你项目里也要写）：这个系统只做**信息检索与资格条款解释**，不提供医疗建议；最终是否适合参加试验必须由临床医生/研究团队确认。

---

## 1) 这个项目到底解决什么问题

### 背景痛点

临床试验（clinical trials）对很多患者很重要，但现实里“找试验/判断是否符合入组条件”非常难，原因是：

* 试验数量巨大、信息分散；
* **Eligibility criteria（入排标准）通常是一大段非结构化文本**，里面包含年龄、疾病史、用药、化验指标阈值、时间窗（过去 3 个月/6 个月）、排除项（no history of …）等；
* 即使找到试验，也很难快速知道“我到底卡在哪条”。

ClinicalTrials.gov 提供了公开数据与 **Data API**，可以程序化获取试验记录。([National Library of Medicine][1])
但它只给“原始文本”，没有现成的“可计算规则”，所以你要做的 AI 价值就在这里。

### 你的产品形态（面向真实用户的“可用系统”）

做一个网页/应用，用户输入一个“患者画像”（你可以用合成数据，不用真实隐私数据），系统输出：

1. **Top-K 可能合适的试验列表**（可按疾病/城市/招募状态筛选）
2. 每个试验的**资格条款逐条解释**：

   * ✅ 满足（并指出依据：年龄/诊断/用药/化验）
   * ❌ 不满足（指出是哪条排除项）
   * ❓ 不确定（缺少信息，需要人工确认）
3. 一键导出一份“试验沟通摘要”（给医生/研究助理看的 checklist）

---

## 2) 数据从哪里来（公开、稳定、可复现）

### A. 试验数据：ClinicalTrials.gov Data API

* ClinicalTrials.gov 在现代化版本中提供 **API v2.0**，是 REST API，JSON 为主响应格式，并使用 OpenAPI 3.0 描述。([National Library of Medicine][1])
* 你会重点用到的字段（概念层面）通常包括：

  * NCT 号、标题、疾病/条件、招募状态、地点
  * **eligibility criteria 文本**（核心）
  * 性别/年龄等结构化限制（很多试验会有）

> 具体字段名以 API 返回为准；你项目里可以把“字段映射表/数据字典”当作交付物的一部分。

### B. 患者数据：用 Synthea 生成合成患者（避免隐私雷）

Synthea 是开源的“合成患者/合成健康记录生成器”，目标是输出**逼真但不是真人**的患者与健康记录，并支持多种导出格式，包括 **HL7 FHIR（R4 等）**、CSV 等。([GitHub][2])

你可以用它生成不同年龄、性别、疾病史组合的“患者画像”，安全、可分享、可放 GitHub。

---

## 3) 这个项目的“AI 核心”是什么（不是简单爬数据）

AI 核心点不是“把 trial 列出来”，而是把 **eligibility criteria 文本 → 结构化可计算规则**，并且能解释。

你可以把它拆成三层（推荐这种工程化路线：先能用，再变强）：

### 层 1：可控的规则抽取（Rule-based baseline，最快跑通）

目标：先把最常见、最规则的条款做掉，保证系统“下限可用”。

典型规则：

* 年龄：`18-65`、`>= 18`
* 性别：male/female/all
* 关键词硬排除：pregnant、renal failure、history of stroke…（先做简单版）

优点：稳定、可解释、没有“胡编”的风险。
缺点：覆盖率有限。

### 层 2：NLP/LLM 结构化抽取（提升覆盖率与可读性）

把一条条标准抽成这种结构（你可以自定义 schema）：

```text
{
  type: "INCLUSION" | "EXCLUSION",
  concept: "HbA1c" | "stroke" | "metformin" | "pregnancy" | ...,
  operator: "<=" | ">=" | "NO_HISTORY" | "WITHIN_LAST" | ...,
  value: 8.0,
  unit: "%",
  time_window: "3 months",
  certainty: "high" | "medium" | "low"
}
```

这里 LLM 的用法很清晰：**信息抽取（IE）** + **文本规范化**，而不是直接让它“判断是否能参加试验”。

你还可以加入两条“安全护栏”：

* 抽取失败/不确定 → 标记为 ❓ 需要人工确认（不要硬判）
* 让模型输出**证据片段**：告诉你它从哪句话抽出来的（减少幻觉）

（想更研究一点）你还可以引用学术界对“eligibility criteria 知识库/结构化抽取”的方向做背景说明，例如 CTKB 之类的工作。([PMC][3])

### 层 3：匹配排序 + 解释（从“抽取”走向“可用产品”）

抽取只是第一步，真正让它像“系统”的是匹配与解释逻辑：

* **Hard filter（硬性淘汰）**
  例如：年龄不符、性别不符、明确排除项命中 → 直接淘汰或降权很大
* **Soft scoring（软评分）**
  条款满足越多、关键条款满足越多 → 分越高
* **Uncertainty-aware ranking（考虑不确定性）**
  如果很多条款是 ❓，不要给特别高的“确定性分数”，而是提示“需要补充哪些信息”。

---

## 4) 系统架构怎么做（像你滇池项目那样端到端）

你可以把它设计成 5 个模块，最后用一个 Dashboard 串起来（非常适合你之前的工程经验）。

### 模块 A：Trial 数据拉取与增量更新

* 定时任务（每天/每周）调用 Data API 拉取你关心的条件/地区的试验
* 存到数据库（Postgres / SQLite 都行）
* 记录更新时间、版本（保证可复现）

ClinicalTrials.gov 的 API v2 是面向现代化网站的 REST API，适合做这种定期更新管线。([National Library of Medicine][1])gibility 文本预处理

* 切分 inclusion / exclusion 两段（很多试验文本里有明显标题）
* 句子级拆分（便于抽取与对齐证据）
* 常见缩写归一（例如 DM2 / T2D）

### 模块 C：Criteria Parser（AI 核心服务）

输入：一段标准文本
输出：结构化规则列表（带证据与置信度）

你可以做成一个独立服务（FastAPI），这样你的前端只要调用它。

### 模块 D：Patient Profile 构建

* 如果你用 Synthea：它能导出 FHIR/CSV，你写一个解析器把患者信息转成你内部的 profile（age、sex、conditions、meds、labs、procedures 等）。([GitHub][2])
* 也可以支持“手动填表模式”（更像真实用户使用）

### 模块 E：Matching & Explanation Engine

* 把 trial 的结构化规则与 patient profile 对齐
* 输出三色结果（✅/❌/❓）和“缺什么信息”

---

## 5) 你在 UI 上怎么呈现，才能“像产品”

我建议你做一个很直观的界面（Streamlit 最快）：

1. 左侧：患者画像输入

* 年龄/性别/主要诊断/关键化验值（可选）/用药（可选）

2. 中间：候选试验列表（Top-K）

* 可按 “距离/招募状态/phase”排序
* 每个试验显示一个“匹配度条”（但要写清楚是估计）

3. 右侧：点开某试验 → 展示 Eligibility Checklist

* Inclusion：逐条 ✅/❌/❓
* Exclusion：命中排除项会特别高亮
* 最下面输出 “Next steps：需要补充哪些信息/建议联系研究团队确认哪些点”

> 你会发现这个 UI 的逻辑跟你滇池 dashboard 很像：把复杂的算法结果做成“可审计、可追溯、可使用”的界面。

---

## 6) 评估怎么做（让它不像 demo，而像“研究+工程”）

### A. 抽取评估（最关键）

做一个小型标注集：

* 随机抽 50–100 个 trial
* 每个 trial 抽 3–5 条标准
* 手工标注你关心的结构化元素（概念、运算符、阈值、时间窗、in/ex）

然后报告：

* precision / recall（至少对 “年龄/性别/时间窗/否定”这种高频元素）
* 错误类型分析：否定理解错、时间窗漏掉、单位换算错、概念同义词没对齐等

### B. 匹配质量（轻量但够用）

* 把 trial-match 视为信息检索任务：你可完全不符）”作为 sanity check
* 或者设置一批合成患者 + 人工挑选“应该匹配的试验类型”，算 Top-K 命中率

### C. 公平性分析（加分项）

用合成患者做群体对比（注意：这只是演示方法，不代表真实世界结论）：

* 不同年龄段、性别、基础病组合的 “eligible rate / uncertain rate / excluded-by-criterion distribution”
* 展示“哪些条款最常导致某群体被排除”（这在 policy narrative 上很好写）

---

## 7) 你最终能交付什么（最适合放 GitHub/简历）

我建议你把交付物做成“4 件套”：

1. **可运行的 Web App**（TrialMatch）
2. **数据与模型管线**（拉取、清洗、解析、索引、匹配）
3. **评估报告**（抽取指标 + 错误分析 + 公平性实验）
4. **README + 风险声明**（非医疗建议、局限性、数据来源说明）

并且在 README 里写清楚：

* 数据来自 ClinicalTrials.gov（公开数据 & API v2）([National Library of Medicine][1])
* 患者数据来自 Synthea（合成、非真实个人数据）([GitHub][2])

---

## 8) 3 周版本的“详细里程碑”（你照着做就能成）

### 第 1 周：跑通 MVP（不需要 LLM）

* 拉取试验数据（按 condition + recruiting status + location）
* 基础 parser：年龄/性别/关键词
* Matching：硬过滤 + 简单排序
* Streamlit 页面：能输入患者 → 出试验列表 → 展示原始 eligibility 文本

### 第 2 周：加入 LLM/NLP 抽取层 + 小评估集

* 句子级切分 inclusion/exclusion
* 抽取 schema 输出（带证据）
* 做 200–300 条标准的人工标注与评估
* 错误分析 + 规则补丁（最能体现你能力）

### 第 3 周：解释体验 + 公平性实验 + 打磨仓库

* Eligibility checklist 视图（✅/❌/❓）
* 合成群体实验（匹配率差异）
* 写技术报告（方法、评估、局限性、伦理声明）

---

## 9) 你想把它做得更“AI”的 3 个升级方向（可选）

1. **向量检索（RAG）做候选召回**
   把试验摘要/条件/标准向量化，先召回候选，再用规则+抽取做精排。

2. **不确定性与校准**
   把 “判定置信度”做得更严格（例如 low certainty 就不下结论）。

3. **标准化医学概念映射**
   把条件/药物/化验映射到标准概念（更鲁棒、可泛化），这会让项目更像 health data science。

---

如果你愿意，我可以继续把它细化到“你可以直接建 repo 开工”的级别：

* 给你一个推荐的目录结构（ingest/parse/match/app/eval）
* 设计你内部的 `criteria_schema.json`
* 给出 10 条最常见 eligibility 模板的规则写法（年龄、妊娠、肾功能、近期用药等）

你只要告诉我：你希望这个项目最终是 **Streamlit 快速 demo**，还是 **FastAPI + 前端更像产品**？

[1]: https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html "ClinicalTrials.gov API Version 2.0 Now Available. NLM Technical Bulletin. 2024 Mar–Apr"
[2]: https://github.com/synthetichealth/synthea "GitHub - synthetichealth/synthea: Synthetic Patient Population Simulator"
[3]: https://pmc.ncbi.nlm.nih.gov/articles/PMC8407851/?utm_source=chatgpt.com "A knowledge base of clinical trial eligibility criteria - PMC"

下面我按“**Leader 给团队下属的项目执行指令**”的口吻，把 **FastAPI + 产品级前端** 的 *Clinical Trial Matching Assistant* 从 0 到最终版完整拆开：**每一步做什么、每个模块要有什么、模块之间怎么对接、从基础版本如何迭代到最终版本**。你照这个拆解推进，完全可行（不依赖任何私有数据；ClinicalTrials.gov 是公开 API；患者侧用 Synthea 合成数据即可）。

---

# 0. 项目北极星与边界（先写死，避免返工）

## 0.1 北极星（我们最终要交付的“像产品”的东西）

一个可以跑在本地/云端的 Web 产品：

* 用户能注册/登录
* 能创建或导入“患者画像”（**只允许合成数据**；或手动填表）
* 能搜索 ClinicalTrials.gov 上的试验（按疾病、招募状态、地理位置等）
* 系统自动给出 Top-K 匹配试验
* 每个试验展示“入排标准 checklist”：✅满足 / ❌不满足 / ❓信息不足（需要人工确认）
* 可保存匹配结果、导出摘要（给医生/研究协调员沟通用）
* 全链路可复现：试验数据缓存入库、解析结果入库、有版本号、可回放

ClinicalTrials.gov 的现代化 API v2 是 REST API，并提供交互式文档；单个试验与检索都能通过 `/api/v2/studies/...` 完成。([国家医学图书馆][1])

## 0.2 明确“我们不做什么”（保证项目一定做得完）

* 不做医疗建议/诊断：**只做信息检索与条款解释**
* 不承诺“准确判定能否入组”：任何 ❓ 都提示“需要研究团队确认”
* 不接真实 EHR、不处理真实个人隐私数据（作品集版本只用 Synthea/手动输入）
* 不做“自动联系试验机构”“一键报名”等高风险功能

## 0.3 成功验收标准（Definition of Done）

* 前端：3 条核心用户路径可顺利走通（见 2.2）
* 后端：OpenAPI 文档完整；关键接口有集成测试；异常时有统一错误码
* 数据：试验拉取可增量更新；解析结果可追溯（raw JSON + parsed JSON）
* AI：解析失败不会影响系统可用性（降级策略必须生效）
* 安全：JWT 登录；基础限流与缓存；敏感输入不落日志

---

# 1. 总体架构（你按这个分模块施工）

我们采用 **“两服务 + 一 worker + 一数据库 + 一缓存”** 的最小可行产品架构（够产品化，但不复杂）：

```
[Next.js Web]  <--HTTPS-->  [FastAPI API Server]
                                   |
                                   | (SQL)
                                [PostgreSQL]
                                   |
                                   | (queue/cache)
                                 [Redis]
                                   |
                                   | (async jobs)
                             [Worker: Celery/RQ]
                                   |
                                   | (fetch)
                         [ClinicalTrials.gov API v2]
```

* ClinicalTrials.gov API v2：我们用它抓取试验详情与检索结果（官方给出了 v2 REST API，且示例中明确 `/api/v2/studies/{nctId}` 可直接拿 JSON）。([国家医学图书馆][2])
* 合成患者：用 Synthea 生成（它输出“合成但逼真”的病人数据，并支持 FHIR/CSV 等格式）。([GitHub][3])

---

# 2. 产品需求拆解（先把用户路径定清楚）

## 2.1 三条必须支持的核心用户路径

> 这三条路径是 MVP 的“必须可用”。任何一条不通，先别做高级 AI。

**路径 A：试验浏览（无患者也能用）**

1. 用户打开 Trial Search
2. 输入 condition（例如 diabetes）+ recruiting 状态
3. 看到试验列表 → 点开详情 → 看到 eligibility 文本与地点

**路径 B：手动建患者画像 + 匹配**

1. 用户创建 Patient Profile（年龄、性别、主要诊断、关键用药/化验可选）
2. 点击 “Find Trials”
3. 返回 Top-K + 每个试验的 checklist（至少能判断年龄/性别/关键词排除项）
4. 用户保存某个 Match result

**路径 C：导入合成患者（Synthea）+ 匹配**

1. 用户上传 Synthea 导出的 FHIR/CSV（作品集：只支持我们规定的子集）
2. 系统生成 Patient Profile
3. 用户跑匹配，得到同样的输出

Synthea 支持输出 FHIR/CSV，且数据“逼真但不是现实个体”，正适合做作品集而不踩隐私。([GitHub][3])

## 2.2 前端页面信息架构（像产品）

* `/login` `/register`
* `/app`（Dashboard：最近匹配、最近患者）
* `/patients`（列表）
* `/patients/new`（创建）
* `/patients/:id`（详情 + 一键匹配）
* `/trials`（搜索页）
* `/trials/:nctId`（试验详情：摘要、eligibility、地点）
* `/matches/:id`（匹配结果：Top-K + checklist）
* `/admin`（仅管理员：数据同步、解析队列、系统健康）

---

# 3. 数据域模型（数据库里必须有哪些表）

> 这部分是“做得像产品”的关键：你不把数据模型想清楚，后面会爆炸返工。

## 3.1 核心表（MVP 就要有）

1. `users`

* id, email, password_hash, role, created_at

2. `patient_profiles`

* id, user_id
* `profile_json`（统一存成 JSON：demographics/conditions/meds/labs）
* source（manual / synthea）
* created_at, updated_at

3. `trials`

* nct_id（唯一）
* title, conditions, status, phase（可选）
* eligibility_text（原始文本）
* locations_json（地点聚合）
* `raw_json`（保存从 API 拿到的原始 JSON，便于追溯）
* `fetched_at`, `source_version`（用于可复现）

ClinicalTrials.gov API v2 提供 JSON 结构化输出（ISO 8601 日期等），适合直接做“raw_json + 结构化字段”的存储策略。([国家医学图书馆][1])

4. `trial_criteria`（解析后的标准）

* id, nct_id
* parser_version（比如 `rule_v1`, `llm_v1`）
* criteria_json（结构化规则数组）
* coverage_stats（解析覆盖率等）
* created_at

5. `matches`

* id, user_id, patient_profile_id
* query_json（当次检索参数：condition/location/status等）
* results_json（Top-K 列表 + score + checklist）
* created_at

## 3.2 为什么要存 raw_json + parsed_json

* 你要能解释：这个匹配结果来自哪个版本的试验记录
* ClinicalTrials.gov 会更新记录，你必须能追溯历史（否则你无法复现实验/演示）
* 解析器迭代时你可以重跑解析并对比版本

---

# 4. 后端（FastAPI）模块分工与接口契约

> 这里开始我用“给下属分任务”的方式写，每个模块都要交付什么、怎么验收。

## 4.1 模块 1：CTGov Client（对外部 API 的唯一出口）

**Owner：Backend / Data**

### 目标

封装 ClinicalTrials.gov API v2，提供两个能力：

* `search_studies(...)`：按条件检索试验（分页）
* `get_study(nct_id)`：获取单个试验完整详情

NLM 的官方说明里给了明确示例：`GET /api/v2/studies/{nctId}` 可直接拿 JSON；并且检索可以通过 `query.cond` 等参数完成。([国家医学图书馆][2])

### 交付物

* `app/services/ctgov_client.py`

  * 统一超时、重试、指数退避
  * 统一错误映射（外部 429/5xx → 我们的错误码）
  * 支持 `pageToken` 分页（避免一次取爆）
* 单元测试：mock 外部 API 响应（成功/失败/分页）

### 验收标准

* 能稳定拉取一个 NCT 试验并写入 `trials.raw_json`
* 能对一个 condition 拉取多页结果（验证 pageToken 流程）

---

## 4.2 模块 2：Trial Ingestion（试验数据入库与增量更新）

**Owner：Data / Backend**

### 目标

让系统不依赖“实时打外部 API”：我们以 **本地数据库为准**，外部 API 只是同步来源。

### 交付物

* `app/services/trial_ingestor.py`

  * `sync_by_condition(condition, status, updated_since?)`
  * upsert 到 `trials` 表
* `worker/tasks.py`

  * 后台任务：同步、解析、索引更新（见 4.5）
* 管理员接口（`/admin/sync`）触发同步任务

### 验收标准

* 同一个 condition 重复 sync 不会产生重复记录（upsert 正确）
* 新试验能新增；更新试验能覆盖结构化字段并保留 raw_json 版本信息

---

## 4.3 模块 3：Trial Search API（对前端提供稳定查询）

**Owner：Backend**

### 目标

前端不直接访问外部 API，只访问我们自己的后端。

### API 设计（MVP）

* `GET /api/trials`

  * query: condition, status, phase, country/state/city（可选）
  * 返回：trial card 列表（nct_id, title, status, short conditions）
* `GET /api/trials/{nct_id}`

  * 返回：完整详情（含 eligibility_text、locations）

### 验收标准

* `/api/trials` 支持过滤 + 分页（我们自己分页）
* `/api/trials/{nct_id}` 一次性返回试验详情（前端可渲染）

---

## 4.4 模块 4：Patient Profile（手动输入 + Synthea 导入）

**Owner：Backend + Frontend**

### 目标

把患者信息统一为一个内部 `PatientProfile` JSON schema，后续匹配引擎只吃这个 schema。

### 内部 Schema（必须固定）

（示例，实际字段按你实现）

```json
{
  "demographics": { "age": 52, "sex": "female" },
  "conditions": ["type 2 diabetes", "hypertension"],
  "medications": ["metformin"],
  "labs": [{ "name": "HbA1c", "value": 7.8, "unit": "%" }],
  "notes": "optional free text"
}
```

### 功能拆解

A) 手动创建

* `POST /api/patients`
* `GET /api/patients/:id`

B) Synthea 导入（作品集版本**只做最小子集**）

* 支持两种导入方式（选一个实现就行）

  1. 上传 Synthea CSV：你解析 `patients.csv`、`conditions.csv`、`medications.csv`、`observations.csv`
  2. 上传 FHIR R4 JSON/ndjson：你解析 Patient / Condition / MedicationRequest / Observation
     Synthea 明确支持导出 HL7 FHIR（含 R4）和 CSV。([GitHub][3])

### 验收标准

* 任意导入/手动创建的患者，最终都能生成同样结构的 `profile_json`

---

## 4.5 模块 5：Criteria Parser（AI 核心，但必须“可降级”）

**Owner：ML/NLP + Backend**

### 核心原则（写进技术规范）

1. **解析器失败 ≠ 系统失败**
2. 任何不确定条款必须输出 `UNKNOWN`，不允许硬判
3. 每条结构化规则必须带 `evidence_text`（从原 eligibility 拿到的句子片段）
4. 解析结果必须通过 JSON Schema / Pydantic 校验，不合格就丢弃并降级

### 解析器分两层迭代（从基础到最终）

**层 1：Rule Parser（MVP 必须完成）**

* 能抽取：

  * 年龄范围/阈值
  * 性别限制
  * 常见排除关键词（pregnant、renal failure、stroke、cancer 等你自定义一小撮）
* 输出统一结构：

```json
{
  "type": "INCLUSION",
  "field": "age",
  "op": ">=",
  "value": 18,
  "unit": "years",
  "certainty": "high",
  "evidence_text": "Participants must be 18 years or older."
}
```

**层 2：LLM Parser（最终版增强）**

* 抽取更复杂的：

  * 时间窗（within last 6 months）
  * 实验室阈值（HbA1c <= 8%）
  * 否定与病史（no history of stroke）
* 仍然要输出同一 schema，并给出 evidence span

> ClinicalTrials.gov API v2 的返回是结构化 JSON + rich-text（CommonMark），适合你做“句子切分→结构化抽取”。([国家医学图书馆][1])

### 后台执行方式（必须异步）

* Worker 消费任务：`parse_trial(nct_id, parser_version)`
* 解析成功写 `trial_criteria`
* 解析失败记录 error + 允许重试

### 验收标准

* 对 100 个试验跑解析：系统不崩；可查看 coverage（解析出多少条规则）
* 任意一个试验解析失败，不影响 `/api/trials/{nct_id}` 返回原文

---

## 4.6 模块 6：Matching Engine（匹配与解释，产品价值所在）

**Owner：Backend + ML**

### 匹配策略（必须可解释）

我们把匹配拆成三步：

**Step 1：候选召回（Candidate Retrieval）**

* MVP：用结构化过滤

  * condition 关键词匹配（title/conditions 字段）
  * recruiting status
  * 地理过滤（country/state/city）
* 最终：加入向量检索（embedding）做语义召回（可选增强，不是必须）

**Step 2：硬规则过滤（Hard Filters）**

* 年龄不符 → 直接 `DISQUALIFIED`
* 性别不符 → 直接 `DISQUALIFIED`
* 明确排除项命中（来自规则层）→ `DISQUALIFIED`

**Step 3：软评分与排序（Soft Scoring）**

* 满足更多 inclusion → 分更高
* exclusion 未命中 → 分更高
* UNKNOWN 多 → 降低“确定性分”，但仍可保留（提示补信息）

### 输出格式（前端渲染必须依赖这个契约）

`POST /api/match`
输入：

* patient_profile_id
* filters（condition/location/status…）
* top_k

输出：

```json
{
  "match_id": "uuid",
  "results": [
    {
      "nct_id": "NCTxxxx",
      "score": 0.82,
      "certainty": 0.63,
      "summary": { "title": "...", "status": "...", "locations": [...] },
      "checklist": {
        "inclusion": [ { "rule_id": "...", "verdict": "PASS|FAIL|UNKNOWN", "evidence": "..." } ],
        "exclusion": [ ... ],
        "missing_info": ["HbA1c value", "pregnancy status"]
      }
    }
  ]
}
```

### 验收标准

* 对同一个患者画像，多次运行输出稳定（同样输入→同样输出）
* checklist 能解释清楚“卡在哪条/缺什么信息”

---

## 4.7 模块 7：Auth、权限、审计（让它像产品而不是 demo）

**Owner：Backend**

### MVP 范围

* JWT 登录（access token + refresh 可选）
* `role=user/admin`
* 管理接口（sync/parse/index）仅 admin 可用
* 请求日志脱敏：不记录患者 notes 原文；记录 patient_id + action_id 即可

### 验收标准

* 未登录不能访问 `/api/patients` `/api/match`
* 非 admin 不能触发 `/admin/sync`

---

# 5. 前端（更像产品的 Next.js）模块拆解

## 5.1 技术决策（统一）

* Next.js + TypeScript
* API 客户端：从 FastAPI 的 OpenAPI 自动生成 TS client（避免手写 fetch 到处散）
* 状态管理：轻量（React Query / SWR + local store）即可
* UI：组件化（TrialCard、Checklist、PatientForm、FilterPanel）

## 5.2 前端组件清单（按页面交付）

**A) PatientForm（最重要）**

* demographics（必填）
* conditions（必填至少 1）
* meds/labs（可选，但要有结构化输入控件：name/value/unit）

**B) TrialSearch**

* filters（condition/status/location）
* trial list + pagination
* trial detail drawer

**C) MatchResults**

* 左侧：Top-K 试验列表
* 右侧：Checklist（inclusion/exclusion 分组，颜色区分 PASS/FAIL/UNKNOWN）
* “missing_info” 自动生成补全提示

**D) AdminConsole**

* 触发 sync
* 查看队列任务状态（成功/失败数）
* 查看系统健康（API/DB/Redis）

---

# 6. 从基础到最终版本：里程碑式交付（不写时间，只写顺序）

> 你按里程碑推进，每个里程碑都能“独立演示”，这就是可行的关键。

## 里程碑 M0：项目骨架与可一键启动

**目标**：任何人 clone 后 `docker compose up` 能看到页面 + API health。

交付：

* monorepo 目录结构
* docker-compose：`web`, `api`, `db`, `redis`, `worker`
* `/healthz`、`/readyz` 两个接口

验收：

* Web 能打开；API 返回健康；DB migration 自动跑

---

## 里程碑 M1：Trial Browser（先让产品“有内容”）

**目标**：不做匹配也能浏览试验。

交付：

* CTGov Client + Trial Ingestion（同步 1–2 个 condition 的试验到 DB）
* `/api/trials` `/api/trials/{nct_id}`
* 前端 Trial Search/Detail 页面

验收：

* 你能在 UI 里搜索 “diabetes” 并打开试验详情
* 详情页展示 eligibility 原文 + 地点 + status

ClinicalTrials.gov 提供公开 REST API 来获取单个试验与按 condition 检索，官方示例明确可用 `/api/v2/studies/{nctId}` 与 condition 查询参数。([国家医学图书馆][2])

---

## 里程碑 M2：Patient Profile（手动）+ Baseline Matching（无 AI 也可用）

**目标**：最基础的匹配闭环跑通。

交付：

* `/api/patients` CRUD（仅手动输入）
* Matching Engine v0：只做年龄/性别硬过滤 + condition 关键词召回
* `/api/match` + `/api/matches/{id}`
* 前端：PatientForm + MatchResults 页面

验收：

* 创建患者→点击匹配→拿到 Top-K→点开 checklist（哪怕只有年龄/性别/少量关键词）

---

## 里程碑 M3：Rule Parser 上线（让 checklist “像回事”）

**目标**：把 eligibility 文本变成结构化规则（基础版）。

交付：

* `trial_criteria` 表
* Worker 异步解析任务（对新 trial 自动 parse）
* checklist 展示基于规则输出（年龄/性别/关键词排除项 + evidence）

验收：

* 解析失败不影响系统运行（必须）
* checklist 每条都有 evidence（可审计）

---

## 里程碑 M4：Synthea 导入（让你能规模化测试与展示公平）

**目标**：不用真人数据也能批量跑匹配。

交付：

* Synthea CSV 或 FHIR 导入器（选一个做深做稳）
* 前端导入页面（上传文件 → 生成患者）
* 可一键生成 10 个合成患者并批量跑匹配（后台任务）

Synthea 支持输出 FHIR/CSV 等多种格式，且是合成患者数据生成器。([GitHub][3])

---

## 里程碑 M5：LLM Parser（最终 AI 增强）+ 评估框架

**目标**：提高解析覆盖率，但保持“可控与可降级”。

交付：

* LLM provider 抽象层（OpenAI/本地模型/关闭模式）
* 严格 JSON schema 输出 + Pydantic 校验 + evidence span
* 解析评估脚本：

  * 抽样 N 条规则人工标注（小规模即可）
  * 输出 coverage、field-level accuracy、常见错误类型
* UI 增强：UNKNOWN 的 missing_info 自动生成更具体提示

验收：

* LLM 不可用时：自动回退 Rule Parser，系统不降级为不可用
* 评估报告可复现（给作品集加分）

---

## 里程碑 M6：产品化收尾（你拿去面试/申请的版本）

交付：

* 限流/缓存：对外部 API 与我们的 `/api/match` 做基本防抖
* Observability：结构化日志 + 关键指标（同步成功率、解析成功率、平均匹配耗时）
* 导出功能：match summary 导出 PDF/JSON（可选）
* 风险声明与合规模块（About 页面）：非医疗建议、仅合成数据、局限性说明

---

# 7. 工程规范（强制执行，不然做不成“产品”）

## 7.1 代码与目录结构（建议）

**repo/**

* `apps/api/`（FastAPI）
* `apps/worker/`（Celery/RQ 任务）
* `apps/web/`（Next.js）
* `packages/shared/`（共享 types、OpenAPI client、常量）
* `infra/`（docker-compose、nginx、db init）
* `docs/`（架构、API 契约、数据字典、风险声明）

## 7.2 质量门槛

* 每个 API endpoint 都要有：

  * 请求/响应 schema
  * 最少 1 个集成测试（happy path）
  * 统一错误码（比如 `TRIAL_NOT_FOUND`, `PARSER_FAILED`）

## 7.3 数据与隐私

* 默认只允许导入 Synthea/手填合成信息
* 前端提示“不输入任何可识别个人身份信息”
* 后端日志脱敏：不打出 profile_json 原文（只打 id）

---

# 8. 风险清单与对策（Leader 必须提前写）

1. **外部 API 限流/不稳定**

   * 对策：本地 DB 缓存 + 增量同步 + 重试退避 + pageToken 分页（官方也提示大数据量要用分页 token）。([国家医学图书馆][2])

2. **LLM 幻觉导致错误结构化**

   * 对策：强 schema 校验 + evidence 必填 + 不确定即 UNKNOWN + 失败回退 rule parser

3. **Eligibility 文本千奇百怪，解析覆盖率不够**

   * 对策：先做“高频、价值最大”的 10 类规则（年龄/性别/妊娠/近期用药/常见病史/实验室阈值/时间窗/器官功能/手术史/肿瘤史）；其余 UNKNOWN

4. **做成 demo 而不是产品**

   * 对策：从 M1 就走“入库→查询→前端”闭环；每个里程碑可独立演示；所有任务有验收标准

---

如果你愿意，我下一步可以把上面内容进一步“落地成可执行的工程任务单（Jira/Todo 风格）”，按模块列出：

* 每个任务的输入/输出、接口、验收用例（curl 命令）、以及依赖顺序。

你只需要告诉我：你更倾向 **Next.js + Tailwind** 还是 **Next.js + MUI/AntD**（只影响 UI 组件库，不影响整体方案）。

[1]: https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html "ClinicalTrials.gov API Version 2.0 Now Available. NLM Technical Bulletin. 2024 Mar–Apr"
[2]: https://www.nlm.nih.gov/pubs/techbull/ja25/ja25_clinical_trials_screen-scraping.html "Does Screen Scraping ClinicalTrials.gov Work?. NLM Technical Bulletin. 2025 Jul–Aug"
[3]: https://github.com/synthetichealth/synthea "GitHub - synthetichealth/synthea: Synthetic Patient Population Simulator"


下面我把你这 5 条反馈（边界/指标、成本、合规、评估、LLM 版本化与降级）全部“落到可执行层面”，给你一份 **Leader 级别的项目方案 v2**：每一步做什么、每个模块有什么、怎么从基础版做到最终版、以及怎么验收。

> 我默认这个项目是：**基于 ClinicalTrials.gov API v2 的临床试验搜索 + 解释产品**（FastAPI 后端 + 前端产品），用 AI 做「自然语言检索→结构化查询」「试验条目/纳排标准的可读化总结」，但 **不做医疗建议**。
> ClinicalTrials.gov API 是公开 REST API（v2），并且可以用 `/api/v2/version` 获取 API 版本和数据更新时间戳。([临床试验.gov][1])

---

# 1) 项目边界（Scope）与非目标（Out of Scope）

## 1.1 你这个产品“只做什么”

**产品目标（In Scope）**：帮助用户更快找到“可能相关”的临床试验，并把官方条目用更好懂的方式呈现。

* **检索**：用户用自然语言描述（疾病/人群/地点/阶段等），系统转成结构化查询，调用 ClinicalTrials.gov API 返回试验列表。
* **理解**：展示每个试验的关键信息（目的、设计、阶段、地点、联系人、主要结局等），并给出“阅读辅助”的 AI 摘要（可选/按需生成）。
* **纳排标准辅助**：把 eligibility criteria 的长文本拆成更可读的条目（并标注“信息来自官方条目，不代表医生判断”）。
* **比较/收藏/导出**：用户可对比 2–3 个试验，收藏列表，导出 CSV/JSON（面向政策/研究分析也有用）。

## 1.2 明确“不做什么”（写进 README + UI 免责声明）

**非目标（Out of Scope）**——这部分非常关键，避免你项目被质疑“越界”：

* **不提供医疗建议/诊断**；不告诉用户“你符合/不符合”；只做信息检索与解释。
* **不接入个人病历/EHR**；不要求用户输入隐私健康信息（PHI）。
* **不做真实报名/预约/招募流程**；只提供官方联系人与链接。
* **不保证条目准确性**；因为 ClinicalTrials.gov 依赖申办方/研究者提交信息。官方也明确：美国政府不审查/批准所有研究的安全性与科学性，NLM 只做有限审查，研究者对其列出的研究的安全性、科学性与准确性负责。

---

# 2) 成功指标（Success Metrics）与验收阈值（Definition of Done）

你提到的 Top‑K 命中率、解析覆盖率、响应时间，我给你一整套**可量化 + 可验收**的定义。

## 2.1 线上（产品）指标：用户体验 + 稳定性

**SLO（服务等级目标）**

1. **搜索接口 P95 响应时间**

   * 不含 LLM：P95 ≤ **1.5s**（缓存命中时 ≤ 400ms）
   * 含 LLM（仅 query 解析）：P95 ≤ **4.0s**
   * 含 LLM（生成摘要）：按需触发，P95 ≤ **8.0s**

2. **可用性**：30 天滚动 API 成功率 ≥ **99.5%**（5xx + 超时算失败）

3. **成本保护**：当日 LLM 成本达到预算 80% 时自动进入“降级模式”（见第 6 部分）

> 注意：ClinicalTrials.gov 数据工作日每日更新（通常美东 9am 前后完成），API 文档建议用 `/api/v2/version` 的 `dataTimestamp` 检查刷新是否完成。([临床试验.gov][2])

## 2.2 离线（算法/能力）指标：可复现评估

### A. Top‑K 命中率（检索是否“找得到”）

**定义**：对每个测试查询 q，有人工标注的“相关试验集合” R(q)。系统返回排序列表 L(q)。
Top‑K HitRate = 平均值 𝟙[ L@K 与 R(q) 有交集 ]。

**验收目标（MVP → V1 → V2）**

* MVP（无 LLM 重排，仅结构化 query）：Top‑10 HitRate ≥ **0.70**
* V1（加入 LLM query 理解 + 规则校验）：Top‑10 HitRate ≥ **0.80**
* V2（可选语义重排/embedding）：Top‑10 HitRate ≥ **0.85**

同时再加一个更稳的排序指标（避免“只要出现就算”太宽松）：

* **nDCG@10 ≥ 0.65（V1），≥ 0.70（V2）**

### B. 解析覆盖率（Parsing Coverage）

这里分两类：

1. **结构化字段覆盖**（来自 API 已结构化的字段：phase、status、minimumAge、sex、locations 等）

* Coverage ≥ **99%**（基本等同“字段存在就能取到”）

2. **非结构化纳排文本解析覆盖**（eligibilityCriteria 文本里提取如：关键排除项、时间窗、药物禁忌、检验指标等）

* Coverage（能输出“结构化条目”且通过校验）≥ **85%**
* 其中“关键约束”（年龄/性别/地理/孕哺/合并症/近期治疗等）抽取 F1 ≥ **0.80**（V2）

### C. 事实一致性（LLM 摘要不胡说）

* **引用一致率**：摘要中所有“可被定位的事实”必须能在官方字段/原文中找到。

  * 验收：抽样 200 条摘要，Hallucination rate ≤ **2%**（严重错误：虚构药物、虚构地点、虚构入组条件）

> 你要做作品集，**有一套严谨评估定义**会让这个项目像真的在做产品/研究，而不是“堆功能”。

---

# 3) 成本/资源假设（你必须写进方案的“财务模型”）

下面给你一个“可落地的成本模型模板”，你可以直接贴到项目文档。

## 3.1 流量与调用假设（可调整）

* DAU：100
* 每人每日搜索：5 次 → 500 searches/day
* 每次搜索返回列表展示：Top 20（但摘要只对 Top 5 默认生成，或点击后生成）
* 每次搜索：

  * CTgov API：1–3 次（考虑分页/补详情）
  * LLM：1 次（query 解析），0–5 次（摘要/纳排解释，按需）

## 3.2 外部 API 调用成本

ClinicalTrials.gov API 本身免费，但有**速率限制风险**。很多第三方实践文档提到大约 **50 req/min/IP** 的量级（你不能把它当成永远正确，但可作为“保守限流的参考”）。([BioMCP][3])
**策略**：我们后端限流设为 **30 req/min/IP（保守）**，遇到 429/5xx 用指数退避 + 队列（见第 5 部分）。

## 3.3 LLM 成本（给出公式，而不是拍脑袋）

你需要在后端记录每次 LLM 调用的 token 数（input/output），然后成本：

* 日成本 ≈ Σ( calls_i × (inTok_i × price_in + outTok_i × price_out) )
* 再加上“最大摘要条数限制”与“按需生成”，把成本上限锁死

**建议预算控制**（你可以用“项目作品集版”预算写法）：

* Budget/day：$2（示例）
* 超过 80% 进入降级
* 超过 100% 禁用摘要，只保留检索与结构化字段展示

## 3.4 部署预算（保证“完全可行”）

* 最小可行：1 台小型云主机（2c4g）+ Postgres（托管或同机）+ Redis（可选）
* 或者 serverless（Cloudflare/Fly/Render）
* 你写方案时要明确：“优先单机部署 + docker-compose，后续可迁移”。

---

# 4) 外部数据依赖的合规：速率限制、缓存、免责声明（必须落地到代码与 UI）

## 4.1 合规原则（写入 README + 页脚）

1. **禁止 screen scraping**：ClinicalTrials.gov 是 SPA，抓 HTML 只会拿到 bootstrap JS，官方也建议用开放 API 获取单个研究与条件检索数据，而不是爬页面。([国家医学图书馆][4])
2. **明确免责声明**：

   * 美国政府不审查/批准所有研究的安全与科学性
   * NLM 仅做有限审查
   * 研究申办方/研究者对信息准确性负责
3. **遵守 Terms & Conditions**：这些条款适用于从 ClinicalTrials.gov 获得的所有数据（不管通过何种方式获得）。([临床试验.gov][5])

> 你的产品页脚建议固定三段：**Data source**（CTgov）、**Not medical advice**、**Terms & Conditions**。

## 4.2 缓存策略（Cache Strategy）——既合规又省钱

我们采用“**版本戳驱动**”缓存：

* 每次启动/定时任务先请求 `/api/v2/version`，拿到 `dataTimestamp`。([临床试验.gov][1])
* 缓存条目存：

  * key：canonical_query（或 nctId）
  * value：响应 JSON（精简版）
  * meta：dataTimestamp、createdAt、ttl

**缓存失效规则：**

* 如果当前 dataTimestamp ≠ 缓存记录的 dataTimestamp → 视为过期（强制刷新）
* 搜索缓存 TTL：6–24 小时（以 dataTimestamp 为准）
* 单个研究详情缓存 TTL：24–72 小时（同时受 dataTimestamp 变化影响）

## 4.3 速率限制与重试（代码层必须有）

* 本地限流器：token bucket（默认 30 req/min/IP）
* 遇到 429：

  * 指数退避：1s → 2s → 4s → 8s（最多 5 次）
  * 仍失败：返回“稍后重试”+ 前端展示“系统繁忙，已降级展示缓存结果”
* 记录：每次 429 的 endpoint、query、重试次数（用于调参）

---

# 5) 评估部分：标注规则、样本量、错误类型框架、验收标准

这一段是你作品集最“硬”的地方：你把它写清楚，招生官/面试官会非常买账。

## 5.1 标注任务 1：检索相关性（用于 Top‑K / nDCG）

**数据集构建**

* 采样 120 个查询（覆盖不同场景）：

  * 单疾病：e.g., “asthma clinical trials in California”
  * 特定人群：pregnant / pediatric / older adult
  * 语言噪声：口语、缩写、拼写错误
  * 政策/公平视角：low-income, uninsured, Spanish speakers（注意不收集个人隐私，只是查询语义）

**标注流程**

* 对每个查询，系统取 Top 30 结果（来自 baseline 结构化查询）
* 标注员给每条 trial 打标签（3 级）：

  * **2 = Relevant**：疾病/干预方向明确匹配，且关键人群/地点约束不冲突
  * **1 = Partially relevant**：主题相关但关键约束缺失/不确定
  * **0 = Not relevant**：不相关或明显冲突（比如疾病不同、完全不在目标地区）

**验收**

* Kappa ≥ 0.6（双人标注 20% 样本）
* HitRate / nDCG 达到第 2 部分阈值

## 5.2 标注任务 2：纳排解析/摘要质量

**样本量**

* 200 个 trials（覆盖不同专科 + 不同复杂度的 eligibilityCriteria）

**标注字段（最小集合）**

* inclusion：年龄、性别、核心疾病、关键检查/既往治疗
* exclusion：孕哺、严重合并症、近期用药/手术、关键实验室阈值
* “不可确定/未提及”必须允许（不强行编）

**错误类型框架（Error Taxonomy）**

1. **Extraction error**：把排除当纳入/漏掉数值阈值
2. **Normalization error**：单位/时间窗错误（e.g., “within 30 days” 变成 30 months）
3. **Hallucination**：原文没有的条件被写进摘要（最高优先级拦截）
4. **Over‑generalization**：把“may”写成“must”

**验收**

* 关键字段（年龄/性别/孕哺/地点）F1 ≥ 0.95
* 复杂字段（实验室阈值/近期治疗）F1 ≥ 0.80
* Hallucination ≤ 2%

---

# 6) LLM 版本化、降级与可复现（最容易被问到的工程点）

你这条反馈非常专业。下面是“能写进系统设计并直接照做”的落地方案。

## 6.1 版本化（Versioning）你要存哪些东西

每次 LLM 调用必须写入日志（DB 或 log storage）：

* `model_provider`、`model_name`、`model_version`（如果提供）
* `prompt_id` + `prompt_version`（你的 prompt 也要版本化）
* `temperature`、`max_tokens`、`top_p` 等参数
* `input_hash`（原文可不存，存 hash + 关键字段，避免隐私风险）
* `output_raw`、`output_json`（通过校验后的结构）
* token 使用量、latency、是否 fallback

> 这样你才能做到：**一次结果 = 可复现配置 + 可追责**。

## 6.2 触发条件（Trigger）与回退逻辑（Fallback）

### A. Query 解析（自然语言 → 结构化查询）

**主路径：LLM → JSON schema 校验 → 查询执行**

* 若 LLM 超时/5xx/429：直接回退到 **Rule-based parser**（关键词 + 手动 filters），并提示“已使用基础检索模式”
* 若 LLM 输出无法通过 JSON schema：

  1. 触发一次“修复提示词”（repair prompt）
  2. 仍失败 → rule-based

### B. 摘要生成（trial → 可读摘要）

**默认按需生成**（强烈建议：列表页不自动生成全部摘要，避免成本爆炸）

* 若当日成本达到预算 80%：列表页隐藏“自动摘要”，只保留“点击生成”
* 若达到 100%：禁用摘要，显示结构化字段 + 原文链接

### C. 事实校验（必须有“硬门槛”）

摘要输出必须通过：

* 引用字段校验：摘要中出现的阶段/地点/年龄/状态必须与结构化字段一致，否则判失败 → 重试一次 → 失败则降级为模板摘要（不调用 LLM）

## 6.3 可复现配置（Reproducibility）

* temperature 默认 0（减少随机性）
* prompt 固化为模板文件（仓库管理）
* 每次发布新 model/prompt 前跑离线评估集

  * 若 Top‑10 HitRate 下降 > 3pp 或 Hallucination 上升 > 1pp：禁止上线，或自动回滚到上一版本（配置切换即可）

---

# 7) 从基础到最终版本：按“交付物 + 验收点”拆解（Leader 给下属的执行清单）

下面我按 **V0 → V1 → V2 → V3** 给你完整路径。每个版本都可独立上线演示，保证“完全可行”。

---

## V0（基础可运行版：无 LLM）

目标：**先把产品跑起来**，数据链路、分页、缓存、前后端闭环都通。

### 后端（FastAPI）

**模块 1：CTgov Client**

* `GET /api/v2/version` 拉版本与 dataTimestamp（启动时 + 定时）([临床试验.gov][1])
* `get_study(nctId)`：获取单研究 JSON（可参考 NLM 给的单研究 API 用法）([国家医学图书馆][4])
* `search_studies(params)`：条件检索 + pageToken 分页（必须实现分页，不然结果不完整）([国家医学图书馆][4])

**模块 2：Cache**

* 内存/Redis 任选（先用 Redis 更像产品）
* cache key 规范化：排序 params、去空格、lowercase
* 缓存绑定 dataTimestamp：timestamp 变化自动失效

**模块 3：API 层**

* `GET /health`
* `GET /version`（返回你系统的 dataTimestamp）
* `GET /search`（结构化参数：cond, country, status, phase…）
* `GET /study/{nctId}`

**验收点**

* 能搜、能翻页、能打开详情
* 断网/外部 API 失败时返回明确错误码 + 前端可展示
* 缓存命中率可在日志里看到

### 前端

* Search 页面：输入 + filters（地点/阶段/状态）
* Results 页面：列表 + 分页/“加载更多”
* Detail 页面：结构化字段展示 + 原文链接

---

## V1（加入 LLM：Query 理解 + 轻量摘要）

目标：让用户“用人话能搜到”。

### 后端新增模块

**模块 4：Query Understanding（LLM 可插拔）**

* 输入：用户自然语言（不含隐私）
* 输出：结构化 JSON（你定义 schema：cond、keywords、geo、phase、status、age/sex if any）
* 校验：pydantic schema + 白名单字段
* 回退：rule-based（永远保证可用）

**模块 5：Summary（按需）**

* `POST /study/{nctId}/summary`：只在用户点击时生成
* 输出：

  * “一句话概述”
  * “目的/设计/参与者/地点/联系人”
  * “你需要确认的问题（非医疗建议）”

**验收点**

* 离线评估：Top‑10 HitRate ≥ 0.80（见第 2 部分）
* 成本：每天摘要调用次数上限（配置项）
* 摘要页固定免责声明（引用官方不背书）

---

## V2（纳排解释 + 质量门槛 + 评估体系）

目标：让项目从“能用”变成“可证明有效”。

### 后端新增模块

**模块 6：Eligibility Explainer**

* 输入：eligibilityCriteria 原文
* 输出：结构化条目（inclusion/exclusion 列表）
* 强制错误处理：

  * 若无法解析 → 输出“无法可靠抽取，请阅读原文”而不是胡写

**模块 7：Evaluation Harness（离线评估管线）**

* `eval/` 脚本：跑 Top‑K、nDCG、F1、Hallucination rate
* 标注数据格式：jsonl（query、trial_id、label）

**验收点**

* 解析覆盖率 ≥ 85%，Hallucination ≤ 2%
* 每次发布有 eval 报告（你作品集里可以截图）

---

## V3（产品化增强：收藏/对比/多语言/可访问性）

目标：更像“真实产品”，也更贴合公平/公共服务方向。

**模块 8：User layer（可选）**

* 匿名也可用；登录仅用于收藏/对比
* 不采集健康隐私

**模块 9：多语言与可读性**

* 摘要支持中英/西语（按需）
* 生成“plain language”版本（参考 ClinicalTrials.gov 自己也强调 plain language 的价值）([临床试验.gov][6])

**模块 10：公平视角展示（加分项）**

* 地图/距离（仅用 trial location）
* 试验分布与趋势分析（政策/公共服务角度）

---

# 8) 你下一步最该做什么（按优先级）

如果你现在就要开工，我建议你严格按这个顺序：

1. **先做 V0**：把 CTgov client + 分页 + 缓存 + 前后端闭环跑通
2. 再加 **V1 的 query LLM**（只做 1 次 LLM 调用，成本可控）
3. 再做 **V1 的按需摘要**（点击生成）
4. 然后立刻补上 **评估数据集 + 指标报表**（这一步决定项目“含金量”）
5. 最后才是高级功能（纳排解释、对比、收藏、多语言）

---

如果你愿意，我可以在你这个 v2 方案基础上，**直接把：**

* 结构化 JSON schema（query schema / summary schema / eligibility schema）
* FastAPI 路由清单（每个 endpoint 的 request/response）
* 前端页面信息架构（IA）+ 每页组件清单
* 以及一份“评估标注指南（可直接给标注员用）”

也一并写出来，让你可以直接开始实现。

[1]: https://clinicaltrials.gov/api/v2/version "clinicaltrials.gov"
[2]: https://clinicaltrials.gov/data-api/api?utm_source=chatgpt.com "ClinicalTrials.gov API"
[3]: https://biomcp.org/backend-services-reference/04-clinicaltrials-gov/?utm_source=chatgpt.com "ClinicalTrials.gov API"
[4]: https://www.nlm.nih.gov/pubs/techbull/ja25/ja25_clinical_trials_screen-scraping.html "Does Screen Scraping ClinicalTrials.gov Work?. NLM Technical Bulletin. 2025 Jul–Aug"
[5]: https://clinicaltrials.gov/about-site/terms-conditions?utm_source=chatgpt.com "Terms and Conditions | ClinicalTrials.gov"
[6]: https://clinicaltrials.gov/submit-studies/prs-help/plain-language-guide-write-brief-summary?utm_source=chatgpt.com "Plain Language Guide to Write a Brief Summary"
