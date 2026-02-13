export type RuleType = "INCLUSION" | "EXCLUSION";

export type RuleMeta = {
  type?: RuleType | string | null;
  field?: string | null;
  operator?: string | null;
  value?: string | number | string[] | null;
  unit?: string | null;
  time_window?: string | null;
  certainty?: string | null;
};

const FIELD_LABEL: Record<string, string> = {
  age: "age",
  sex: "sex",
  condition: "condition",
  medication: "medication",
  lab: "lab value",
  procedure: "procedure",
  history: "history",
  other: "criterion",
};

const OPERATOR_LABEL: Record<string, string> = {
  ">=": "at least",
  "<=": "at most",
  "=": "equals",
  IN: "includes",
  NOT_IN: "does not include",
  NO_HISTORY: "has no history of",
  WITHIN_LAST: "within last",
  EXISTS: "has",
  NOT_EXISTS: "does not have",
};

function formatValue(value: RuleMeta["value"]) {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(", ");
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

export function narrateRule(meta: RuleMeta): string {
  const field = FIELD_LABEL[String(meta.field ?? "").toLowerCase()] ?? "criterion";
  const operator =
    OPERATOR_LABEL[String(meta.operator ?? "").toUpperCase()] ??
    String(meta.operator ?? "").trim();
  const value = formatValue(meta.value);
  const unit = meta.unit ? ` ${meta.unit}` : "";
  const timeWindow = meta.time_window ? ` (${meta.time_window})` : "";
  const head =
    String(meta.type ?? "").toUpperCase() === "EXCLUSION" ? "Excludes if" : "Requires";

  if (!operator && !value) {
    return `${head} ${field}${timeWindow}`.trim();
  }

  return `${head} ${field} ${operator} ${value}${unit}${timeWindow}`
    .replace(/\s+/g, " ")
    .trim();
}
