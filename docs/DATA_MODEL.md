Data Model

**数据库选择**
- PostgreSQL
- JSONB 用于半结构化字段

**表结构与设计理由**
users
用途: 鉴权与权限控制
字段
- id UUID PK
- email TEXT UNIQUE NOT NULL
- password_hash TEXT NOT NULL
- role TEXT NOT NULL DEFAULT 'user'
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

patient_profiles
用途: 存储患者画像, 便于可复现匹配
字段
- id UUID PK
- user_id UUID FK -> users.id
- profile_json JSONB NOT NULL
- source TEXT NOT NULL DEFAULT 'manual'
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

trials
用途: 存储试验详情与原始 JSON
字段
- id UUID PK
- nct_id TEXT UNIQUE NOT NULL
- title TEXT NOT NULL
- conditions TEXT[]
- status TEXT
- phase TEXT
- eligibility_text TEXT
- locations_json JSONB
- raw_json JSONB NOT NULL
- fetched_at TIMESTAMP NOT NULL
- data_timestamp TIMESTAMP NOT NULL
- source_version TEXT
- created_at TIMESTAMP NOT NULL
- updated_at TIMESTAMP NOT NULL

trial_criteria
用途: 存储解析后的结构化规则
字段
- id UUID PK
- trial_id UUID FK -> trials.id
- parser_version TEXT NOT NULL
- criteria_json JSONB NOT NULL
- coverage_stats JSONB
- created_at TIMESTAMP NOT NULL

matches
用途: 存储匹配结果与可复现查询
字段
- id UUID PK
- user_id UUID FK -> users.id
- patient_profile_id UUID FK -> patient_profiles.id
- query_json JSONB NOT NULL
- results_json JSONB NOT NULL
- created_at TIMESTAMP NOT NULL

**索引建议**
- trials(nct_id)
- trials(status)
- trials(phase)
- trials(fetched_at)
- trial_criteria(trial_id, parser_version)
- matches(user_id, created_at)
- patient_profiles(user_id, created_at)

**Patient Profile 结构**
```json
{
  "demographics": {"age": 52, "sex": "female"},
  "conditions": ["type 2 diabetes"],
  "medications": ["metformin"],
  "labs": [{"name": "HbA1c", "value": 7.8, "unit": "%"}],
  "procedures": [],
  "notes": "optional"
}
```

**版本化与可追溯**
- trials.raw_json 与 trials.data_timestamp 必须保留
- trial_criteria.parser_version 用于比较不同解析版本
- matches.query_json 保存检索参数

**数据一致性约定**
- trials.nct_id 作为外部唯一键
- raw_json 永远保存最新版本
- fetched_at 为本次同步时间
