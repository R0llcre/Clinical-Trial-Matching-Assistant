Matching Logic

**目标**
- 输出 Top-K 试验
- 每条试验附带可解释 checklist
- 明确 PASS, FAIL, UNKNOWN

**输入**
- patient_profile
- filters: condition, status, location, phase
- trial_criteria

**匹配步骤**
1. 候选召回
根据 condition 与关键词检索 trials
按 status, phase, location 过滤
召回上限固定, 例如 500

2. 规则判定
对每条规则生成 verdict
PASS: patient_profile 满足规则
FAIL: patient_profile 明确不满足
UNKNOWN: 信息不足或无法判断

3. 硬规则过滤
年龄、性别、明确排除项 FAIL -> 试验判定为 FAIL
硬规则失败的试验仍可展示, 但排序降到末尾

4. 软评分
PASS: +1
UNKNOWN: +0.3
FAIL: -2
可按规则类型加权, 如 lab 权重 1.2

5. 置信度
certainty = PASS 规则数 / 总规则数
UNKNOWN 越多置信度越低

6. 结果排序
score 高优先
certainty 次优先
更新时间作为最后排序因子

**缺失信息判定**
- rule.field 在 profile 中缺失或为空
- lab, medication, history 不存在时加入 missing_info

**输出结构**
```json
{
  "nct_id": "NCT123",
  "score": 0.82,
  "certainty": 0.64,
  "checklist": {
    "inclusion": [{"rule_id": "rule-1", "verdict": "PASS", "evidence": "..."}],
    "exclusion": [{"rule_id": "rule-2", "verdict": "UNKNOWN", "evidence": "..."}],
    "missing_info": ["HbA1c", "pregnancy status"]
  }
}
```
