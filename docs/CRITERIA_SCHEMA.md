Criteria Schema

**目标**
- 将 eligibility criteria 文本转为结构化规则
- 每条规则必须包含证据片段
- 不确定条款返回 UNKNOWN

**规则对象**
```json
{
  "id": "rule-uuid",
  "type": "INCLUSION|EXCLUSION",
  "field": "age|sex|condition|medication|lab|procedure|history|other",
  "operator": ">=|<=|=|IN|NOT_IN|NO_HISTORY|WITHIN_LAST|EXISTS|NOT_EXISTS",
  "value": "18",
  "unit": "years",
  "time_window": "6 months",
  "certainty": "high|medium|low",
  "evidence_text": "Participants must be 18 years or older.",
  "source_span": {"start": 120, "end": 165}
}
```

**字段约定**
age
- value 数字
- unit 固定 years

sex
- value in [male, female, all]

lab
- value 数值
- unit 规范化

time_window
- 格式: "30 days" 或 "6 months"

**操作符说明**
- >=, <=, =: 数值或枚举比较
- IN, NOT_IN: 列表包含判断
- NO_HISTORY: 既往史排除
- WITHIN_LAST: 时间窗判断
- EXISTS, NOT_EXISTS: 项存在性判断

**UNKNOWN 规则**
- 当无法可靠解析时, field=other, operator=EXISTS, certainty=low
- 必须保留 evidence_text 以便人工核对

**示例规则**
年龄
```json
{"type":"INCLUSION","field":"age","operator":">=","value":18,"unit":"years","certainty":"high","evidence_text":"Participants must be 18 years or older."}
```

性别
```json
{"type":"INCLUSION","field":"sex","operator":"=","value":"female","certainty":"high","evidence_text":"Female participants only."}
```

实验室阈值
```json
{"type":"INCLUSION","field":"lab","operator":"<=","value":8.0,"unit":"%","certainty":"medium","evidence_text":"HbA1c must be <= 8%."}
```

时间窗
```json
{"type":"EXCLUSION","field":"procedure","operator":"WITHIN_LAST","value":6,"unit":"months","certainty":"medium","evidence_text":"No surgery within the last 6 months."}
```
