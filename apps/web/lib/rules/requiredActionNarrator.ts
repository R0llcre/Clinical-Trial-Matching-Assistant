export type RuleMetaLike = {
  field?: string | null;
  operator?: string | null;
  value?: unknown;
  unit?: string | null;
  time_window?: string | null;
  type?: string | null;
  certainty?: string | null;
};

export type RequiredActionNarration = {
  title: string;
  detail?: string;
};

const normalize = (value: string | null | undefined) => (value ?? "").trim();

const normalizeKey = (value: string | null | undefined) =>
  normalize(value).toUpperCase();

export function friendlyMissingField(missingField?: string | null): string {
  const raw = normalize(missingField);
  if (!raw) {
    return "";
  }

  const key = raw.toLowerCase();
  if (key === "demographics.age") {
    return "patient age";
  }
  if (key === "demographics.sex") {
    return "patient sex";
  }
  if (key === "conditions") {
    return "patient conditions / diagnoses";
  }
  if (key === "history") {
    return "medical history";
  }
  if (key === "procedures") {
    return "procedures";
  }
  if (key === "medications") {
    return "medications";
  }
  if (key === "labs") {
    return "lab values";
  }
  if (key === "other") {
    return "clinical notes";
  }
  if (key === "history_timeline") {
    return "history dates";
  }
  if (key === "procedures_timeline") {
    return "procedure dates";
  }
  if (key === "medications_timeline") {
    return "medication dates";
  }
  if (key === "labs_timeline") {
    return "lab dates";
  }

  return raw;
}

const derivedRequiredAction = (missingField?: string | null): string => {
  const key = normalize(missingField).toLowerCase();
  if (!key) {
    return "";
  }
  if (key.startsWith("demographics.age")) {
    return "ADD_DEMOGRAPHIC_AGE";
  }
  if (key.startsWith("demographics.sex")) {
    return "ADD_DEMOGRAPHIC_SEX";
  }
  if (key.startsWith("conditions")) {
    return "ADD_CONDITION";
  }
  if (key.startsWith("labs")) {
    return "ADD_LAB_VALUE";
  }
  if (key.startsWith("history")) {
    return "ADD_HISTORY_TIMELINE";
  }
  if (key.startsWith("procedures")) {
    return "ADD_PROCEDURE_TIMELINE";
  }
  if (key.startsWith("medications")) {
    return "ADD_MEDICATION_TIMELINE";
  }
  if (key.startsWith("other")) {
    return "ADD_PROFILE_NOTES";
  }
  return "";
};

const looksLikeSpecificLabName = (missingField: string) => {
  const key = missingField.trim().toLowerCase();
  if (!key) {
    return false;
  }
  return ![
    "labs",
    "labs_timeline",
    "demographics.age",
    "demographics.sex",
    "conditions",
    "history",
    "history_timeline",
    "procedures",
    "procedures_timeline",
    "medications",
    "medications_timeline",
    "other",
  ].includes(key);
};

export function narrateRequiredAction(args: {
  requiredAction?: string | null;
  missingField?: string | null;
  ruleMeta?: RuleMetaLike;
}): RequiredActionNarration | null {
  const missingFieldRaw = normalize(args.missingField);
  const action =
    normalizeKey(args.requiredAction) || derivedRequiredAction(missingFieldRaw);
  if (!action) {
    return null;
  }

  const operator = normalizeKey(args.ruleMeta?.operator);
  const value = args.ruleMeta?.value;

  if (action === "ADD_DEMOGRAPHIC_AGE") {
    return { title: "Add patient age." };
  }
  if (action === "ADD_DEMOGRAPHIC_SEX") {
    return { title: "Add patient sex." };
  }
  if (action === "ADD_CONDITION") {
    return { title: "Add patient conditions / diagnoses." };
  }
  if (action === "ADD_LAB_VALUE") {
    if (missingFieldRaw && looksLikeSpecificLabName(missingFieldRaw)) {
      return {
        title: `Add lab value: ${missingFieldRaw}.`,
        detail: "Include units and date measured.",
      };
    }
    return {
      title: "Add relevant lab values.",
      detail: "Include units and date measured.",
    };
  }
  if (action === "ADD_HISTORY_TIMELINE") {
    if (operator === "WITHIN_LAST" && typeof value === "string" && value.trim()) {
      return {
        title: `Add the date for: ${value.trim()}.`,
        detail: "To evaluate the time window.",
      };
    }
    return { title: "Add medical history timeline.", detail: "Include dates." };
  }
  if (action === "ADD_PROCEDURE_TIMELINE") {
    return { title: "Add procedure timeline.", detail: "Include dates." };
  }
  if (action === "ADD_MEDICATION_TIMELINE") {
    return { title: "Add medication timeline.", detail: "Include start/end dates." };
  }
  if (action === "ADD_PROFILE_NOTES") {
    return { title: "Add clinical notes relevant to this criterion." };
  }
  if (action === "COLLECT_ADDITIONAL_PROFILE_DATA") {
    return { title: "Add more patient data to evaluate this criterion." };
  }
  if (action === "REVIEW_RULE_MAPPING" || action === "REVIEW_RULE_VALUE") {
    return { title: "Manual review required for this criterion." };
  }

  return { title: "Add more patient data to evaluate this criterion." };
}

