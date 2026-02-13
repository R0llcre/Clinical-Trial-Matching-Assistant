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
  NO_HISTORY: "no history of",
  EXISTS: "includes",
  NOT_EXISTS: "does not include",
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
  const type = String(meta.type ?? "").toUpperCase();
  const fieldKey = String(meta.field ?? "").toLowerCase();
  const operatorKey = String(meta.operator ?? "").toUpperCase();

  const field = FIELD_LABEL[fieldKey] ?? "criterion";
  const value = formatValue(meta.value).trim();
  const unitRaw = String(meta.unit ?? "").trim();
  const unit = unitRaw ? (unitRaw === "%" ? "%" : ` ${unitRaw}`) : "";
  const timeWindowRaw = String(meta.time_window ?? "").trim();
  const timeWindowSuffix = timeWindowRaw ? ` (${timeWindowRaw})` : "";
  const head = type === "EXCLUSION" ? "Excludes if" : "Requires";

  if (operatorKey === "WITHIN_LAST") {
    const term = typeof meta.value === "string" ? meta.value.trim() : "";
    const window =
      timeWindowRaw || (value ? `${value}${unit}`.replace(/\s+/g, " ").trim() : "");
    const within = window ? `within the last ${window}` : "within a recent time window";
    if (term) {
      if (fieldKey === "history") {
        return `${head} history of ${term} ${within}`.replace(/\s+/g, " ").trim();
      }
      return `${head} ${field} ${term} ${within}`.replace(/\s+/g, " ").trim();
    }
    return `${head} ${field} ${within}`.replace(/\s+/g, " ").trim();
  }

  if (fieldKey === "sex" && operatorKey === "=" && value) {
    return `${head} sex is ${value}${timeWindowSuffix}`.replace(/\s+/g, " ").trim();
  }

  if (operatorKey === "NO_HISTORY" && value) {
    return `${head} no history of ${value}${timeWindowSuffix}`
      .replace(/\s+/g, " ")
      .trim();
  }

  if (operatorKey === "EXISTS" && value) {
    return `${head} ${field}: ${value}${unit}${timeWindowSuffix}`
      .replace(/\s+/g, " ")
      .trim();
  }

  if (operatorKey === "NOT_EXISTS" && value) {
    return `${head} no ${field}: ${value}${unit}${timeWindowSuffix}`
      .replace(/\s+/g, " ")
      .trim();
  }

  const operator =
    OPERATOR_LABEL[operatorKey] ?? String(meta.operator ?? "").trim();

  if (!operator && !value) {
    return `${head} ${field}${timeWindowSuffix}`.trim();
  }

  return `${head} ${field} ${operator} ${value}${unit}${timeWindowSuffix}`
    .replace(/\s+/g, " ")
    .trim();
}
