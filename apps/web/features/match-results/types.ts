export type RuleMeta = {
  type?: "INCLUSION" | "EXCLUSION" | string | null;
  field?: string | null;
  operator?: string | null;
  value?: string | number | string[] | null | Record<string, unknown>;
  unit?: string | null;
  time_window?: string | null;
  certainty?: "high" | "medium" | "low" | string | null;
};

export type EvaluationMeta = {
  missing_field?: string | null;
  reason?: string | null;
  reason_code?: string | null;
  required_action?: string | null;
};

export type RuleVerdict = {
  rule_id: string;
  verdict: "PASS" | "FAIL" | "UNKNOWN";
  evidence: string;
  rule_meta?: RuleMeta;
  evaluation_meta?: EvaluationMeta;
};

export type MatchTier = "ELIGIBLE" | "POTENTIAL" | "INELIGIBLE";

export type MatchResultItem = {
  nct_id: string;
  title?: string;
  status?: string;
  phase?: string;
  score: number;
  certainty: number;
  match_summary?: {
    tier: MatchTier;
    pass: number;
    fail: number;
    unknown: number;
    missing: number;
  };
  checklist: {
    inclusion: RuleVerdict[];
    exclusion: RuleVerdict[];
    missing_info: string[];
  };
};

