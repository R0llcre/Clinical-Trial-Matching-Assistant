import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Download,
  Filter,
  ListChecks,
  MapPin,
  RefreshCcw,
  RotateCcw,
  ShieldAlert,
  SlidersHorizontal,
} from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Accordion } from "../../components/ui/Accordion";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Pill } from "../../components/ui/Pill";
import { Skeleton } from "../../components/ui/Skeleton";
import { Toast } from "../../components/ui/Toast";
import { shortId } from "../../lib/format/ids";
import { API_BASE, fetchOk } from "../../lib/http/client";
import { narrateRule } from "../../lib/rules/ruleNarrator";
import {
  friendlyMissingField,
  narrateRequiredAction,
} from "../../lib/rules/requiredActionNarrator";
import {
  clearSessionToken,
  ensureSession as ensureSessionToken,
  getSessionToken,
  withSessionRetry,
} from "../../lib/session/session";
import styles from "./MatchResultsPage.module.css";

type RuleMeta = {
  type?: "INCLUSION" | "EXCLUSION" | string | null;
  field?: string | null;
  operator?: string | null;
  value?: string | number | string[] | null | Record<string, unknown>;
  unit?: string | null;
  time_window?: string | null;
  certainty?: "high" | "medium" | "low" | string | null;
};

type EvaluationMeta = {
  missing_field?: string | null;
  reason?: string | null;
  reason_code?: string | null;
  required_action?: string | null;
};

type RuleVerdict = {
  rule_id: string;
  verdict: "PASS" | "FAIL" | "UNKNOWN";
  evidence: string;
  rule_meta?: RuleMeta;
  evaluation_meta?: EvaluationMeta;
};

type MatchResultItem = {
  nct_id: string;
  title?: string;
  status?: string;
  phase?: string;
  score: number;
  certainty: number;
  match_summary?: {
    tier: "ELIGIBLE" | "POTENTIAL" | "INELIGIBLE";
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

type MatchData = {
  id: string;
  patient_profile_id: string;
  query_json: {
    filters?: Record<string, string>;
    top_k?: number;
  };
  results: MatchResultItem[];
  created_at?: string;
};

type MatchResponse = {
  ok: boolean;
  data?: MatchData;
  error?: {
    code: string;
    message: string;
  };
};

type PatientData = {
  id: string;
  source?: string;
  created_at?: string | null;
  updated_at?: string | null;
  profile_json?: {
    demographics?: {
      age?: number;
      sex?: string;
      [key: string]: unknown;
    };
    conditions?: string[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

type PatientResponse = {
  ok: boolean;
  data?: PatientData;
  error?: {
    code: string;
    message: string;
  };
};

type MatchTier = "ELIGIBLE" | "POTENTIAL" | "INELIGIBLE";
type TierFilter = "ALL" | MatchTier;

const tierLabel: Record<MatchTier, string> = {
  ELIGIBLE: "Strong match",
  POTENTIAL: "Potential",
  INELIGIBLE: "Not eligible",
};

const tierTone: Record<MatchTier, "success" | "warning" | "danger"> = {
  ELIGIBLE: "success",
  POTENTIAL: "warning",
  INELIGIBLE: "danger",
};

const statusLabel = (value?: string | null) => {
  if (!value) {
    return null;
  }
  if (value === "RECRUITING") {
    return "Recruiting";
  }
  if (value === "NOT_YET_RECRUITING") {
    return "Not yet recruiting";
  }
  if (value === "ACTIVE_NOT_RECRUITING") {
    return "Active, not recruiting";
  }
  if (value === "COMPLETED") {
    return "Completed";
  }
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (match) => match.toUpperCase());
};

const statusTone = (
  value?: string | null
): "neutral" | "brand" | "success" | "warning" | "danger" | "info" => {
  if (!value) {
    return "neutral";
  }
  if (value === "RECRUITING") {
    return "success";
  }
  if (value === "NOT_YET_RECRUITING") {
    return "info";
  }
  if (value === "ACTIVE_NOT_RECRUITING") {
    return "brand";
  }
  if (value === "COMPLETED") {
    return "neutral";
  }
  return "neutral";
};

const phaseLabel = (value?: string | null) => {
  if (!value) {
    return null;
  }
  if (value === "EARLY_PHASE1") {
    return "Early Phase 1";
  }
  if (value === "PHASE1") {
    return "Phase 1";
  }
  if (value === "PHASE2") {
    return "Phase 2";
  }
  if (value === "PHASE3") {
    return "Phase 3";
  }
  if (value === "PHASE4") {
    return "Phase 4";
  }
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (match) => match.toUpperCase());
};

const formatIsoDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value.length >= 10 ? value.slice(0, 10) : value;
};

type VerdictCounts = {
  pass: number;
  fail: number;
  unknown: number;
  missing: number;
  totalRules: number;
};

const computeCounts = (item: MatchResultItem): VerdictCounts => {
  const summary = item.match_summary;
  if (summary) {
    const totalRules = summary.pass + summary.fail + summary.unknown;
    return {
      pass: summary.pass,
      fail: summary.fail,
      unknown: summary.unknown,
      missing: summary.missing,
      totalRules,
    };
  }

  const allRules = item.checklist.inclusion.concat(item.checklist.exclusion);
  const pass = allRules.filter((rule) => rule.verdict === "PASS").length;
  const fail = allRules.filter((rule) => rule.verdict === "FAIL").length;
  const unknown = allRules.filter((rule) => rule.verdict === "UNKNOWN").length;
  const missing = item.checklist.missing_info.length;
  return { pass, fail, unknown, missing, totalRules: allRules.length };
};

const tierFromItem = (item: MatchResultItem): MatchTier => {
  const summary = item.match_summary;
  if (summary?.tier) {
    return summary.tier;
  }

  const counts = computeCounts(item);
  if (counts.fail > 0) {
    return "INELIGIBLE";
  }
  if (counts.totalRules === 0) {
    // No evidence should not be shown as a "strong match".
    return "POTENTIAL";
  }
  if (counts.unknown > 0 || counts.missing > 0) {
    return "POTENTIAL";
  }
  return "ELIGIBLE";
};

const downloadJson = (filename: string, data: unknown) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

type MatchSummary = {
  total: number;
  eligible: number;
  potential: number;
  ineligible: number;
};

type ActiveFilter = {
  key: string;
  value: string;
};

type CreateMatchData = {
  match_id: string;
};

const _MAX_PDF_ROWS = 12;

const _formatDateTime = (value?: string | null) => {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

const exportMatchPdf = async ({
  match,
  filters,
  summary,
  patientLabel,
}: {
  match: MatchData;
  filters: ActiveFilter[];
  summary: MatchSummary;
  patientLabel?: string;
}) => {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 40;
  const contentWidth = pageWidth - margin * 2;
  let y = margin;

  const ensureSpace = (neededHeight: number) => {
    if (y + neededHeight <= pageHeight - margin) {
      return;
    }
    doc.addPage();
    y = margin;
  };

  const writeText = (
    text: string,
    {
      size = 11,
      weight = "normal" as "normal" | "bold",
      spacingAfter = 12,
    } = {}
  ) => {
    const lines = doc.splitTextToSize(text, contentWidth) as string[];
    const lineHeight = size + 4;
    ensureSpace(lines.length * lineHeight + spacingAfter);
    doc.setFont("helvetica", weight);
    doc.setFontSize(size);
    for (const line of lines) {
      doc.text(line, margin, y);
      y += lineHeight;
    }
    y += spacingAfter;
  };

  writeText("Clinical Trial Matching Summary", {
    size: 18,
    weight: "bold",
    spacingAfter: 8,
  });
  writeText(`Match ID: ${match.id}`, { size: 10, spacingAfter: 6 });
  writeText(`Created: ${_formatDateTime(match.created_at)}`, {
    size: 10,
    spacingAfter: 16,
  });

  writeText("Patient & filters", { size: 13, weight: "bold", spacingAfter: 6 });
  if (patientLabel) {
    writeText(`Patient: ${patientLabel}`, { spacingAfter: 6 });
  }
  writeText(`Patient ID: ${shortId(match.patient_profile_id)}`, { spacingAfter: 6 });
  if (filters.length === 0) {
    writeText("Filters: none", { spacingAfter: 14 });
  } else {
    writeText(
      `Filters: ${filters.map((entry) => `${entry.key}=${entry.value}`).join(" | ")}`,
      { spacingAfter: 14 }
    );
  }

  writeText("Tier summary", { size: 13, weight: "bold", spacingAfter: 6 });
  writeText(
    `Strong match: ${summary.eligible} | Potential: ${summary.potential} | Not eligible: ${summary.ineligible} | Total: ${summary.total}`,
    { spacingAfter: 14 }
  );

  writeText(`Top trials (first ${Math.min(match.results.length, _MAX_PDF_ROWS)})`, {
    size: 13,
    weight: "bold",
    spacingAfter: 8,
  });

  const rows = match.results.slice(0, _MAX_PDF_ROWS);
  if (rows.length === 0) {
    writeText("No results in this match.", { spacingAfter: 0 });
  } else {
    rows.forEach((item, index) => {
      const tier = tierLabel[tierFromItem(item)];
      writeText(
        `${index + 1}. ${item.nct_id} | ${tier} | score ${item.score.toFixed(2)}`
      );
      writeText(item.title || "(no title)", { size: 10, spacingAfter: 10 });
    });
  }

  doc.save(`match-${match.id}.pdf`);
};

const pickFilters = (filters?: Record<string, string>) => {
  const entries = Object.entries(filters ?? {}).filter(([_, v]) => String(v).trim());
  return entries.map(([k, v]) => ({ key: k, value: String(v) }));
};

const ruleGroups = (rules: RuleVerdict[]) => {
  const byVerdict: Record<RuleVerdict["verdict"], RuleVerdict[]> = {
    PASS: [],
    FAIL: [],
    UNKNOWN: [],
  };
  for (const rule of rules) {
    byVerdict[rule.verdict].push(rule);
  }
  return byVerdict;
};

const passSectionKey = (nctId: string, section: "inclusion" | "exclusion") =>
  `${nctId}:${section}`;

const verdictTone: Record<
  RuleVerdict["verdict"],
  "success" | "warning" | "danger"
> = {
  PASS: "success",
  FAIL: "danger",
  UNKNOWN: "warning",
};

const summarizeRule = (rule: RuleVerdict) => {
  if (rule.rule_meta) {
    return narrateRule({
      type: rule.rule_meta.type,
      field: rule.rule_meta.field,
      operator: rule.rule_meta.operator,
      value: rule.rule_meta.value as
        | string
        | number
        | string[]
        | null
        | undefined,
      unit: rule.rule_meta.unit,
      time_window: rule.rule_meta.time_window,
      certainty: rule.rule_meta.certainty,
    });
  }
  return rule.evidence || "Eligibility criterion";
};

const summarizeRuleMeta = (rule: RuleVerdict) => {
  const meta = rule.rule_meta;
  if (!meta) {
    return "";
  }
  const details = [
    meta.field ? `field: ${meta.field}` : null,
    meta.operator ? `operator: ${meta.operator}` : null,
    meta.value !== null && meta.value !== undefined
      ? `value: ${
          typeof meta.value === "object" ? JSON.stringify(meta.value) : String(meta.value)
        }`
      : null,
    meta.unit ? `unit: ${meta.unit}` : null,
    meta.time_window ? `window: ${meta.time_window}` : null,
    meta.certainty ? `certainty: ${meta.certainty}` : null,
  ].filter(Boolean);
  return details.join(" · ");
};

const whyFromReasonCode = (reasonCode?: string | null) => {
  const code = (reasonCode ?? "").trim().toUpperCase();
  if (!code) {
    return "";
  }
  if (code === "MISSING_FIELD") {
    return "Missing required patient data.";
  }
  if (code === "NO_EVIDENCE") {
    return "Not enough structured information to evaluate this criterion.";
  }
  if (code === "UNSUPPORTED_OPERATOR") {
    return "This criterion uses an operator not yet supported.";
  }
  if (code === "INVALID_RULE_VALUE") {
    return "This criterion has an invalid or incomplete value.";
  }
  return "Unable to evaluate this criterion.";
};

const patientSummaryLine = (patient: PatientData | null): string => {
  if (!patient) {
    return "";
  }

  const conditions = patient.profile_json?.conditions;
  const primaryCondition = Array.isArray(conditions)
    ? (conditions.find((entry) => typeof entry === "string" && entry.trim()) ?? "").trim()
    : "";

  const demographics = patient.profile_json?.demographics;
  const sex =
    typeof demographics?.sex === "string" ? demographics.sex.trim() : "";
  const ageRaw = demographics?.age;
  const age =
    typeof ageRaw === "number" && Number.isFinite(ageRaw)
      ? Math.trunc(ageRaw)
      : null;

  const parts = [
    primaryCondition,
    sex,
    age !== null ? `${age}y` : "",
  ].filter(Boolean);

  return parts.join(" · ");
};

const patientPdfLabel = (patient: PatientData | null): string => {
  if (!patient) {
    return "";
  }

  const conditions = patient.profile_json?.conditions;
  const primaryCondition = Array.isArray(conditions)
    ? (conditions.find((entry) => typeof entry === "string" && entry.trim()) ?? "").trim()
    : "";

  const demographics = patient.profile_json?.demographics;
  const sex =
    typeof demographics?.sex === "string" ? demographics.sex.trim() : "";
  const ageRaw = demographics?.age;
  const age =
    typeof ageRaw === "number" && Number.isFinite(ageRaw)
      ? Math.trunc(ageRaw)
      : null;

  const suffixParts: string[] = [];
  if (sex) {
    suffixParts.push(sex);
  }
  if (age !== null) {
    suffixParts.push(`${age}y`);
  }

  const base = primaryCondition || (suffixParts.length > 0 ? "Patient" : "");
  if (!base) {
    return "";
  }

  return suffixParts.length > 0 ? `${base} (${suffixParts.join(", ")})` : base;
};

export default function MatchResultsPage() {
  const router = useRouter();
  const { id } = router.query;

  const [sessionToken, setSessionToken] = useState(
    process.env.NEXT_PUBLIC_DEV_JWT ?? ""
  );
  const [data, setData] = useState<MatchData | null>(null);
  const [patient, setPatient] = useState<PatientData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedByTrial, setExpandedByTrial] = useState<Record<string, boolean>>(
    {}
  );
  const [showPassBySection, setShowPassBySection] = useState<Record<string, boolean>>(
    {}
  );
  const [tierFilter, setTierFilter] = useState<TierFilter>("ALL");
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportPdfError, setExportPdfError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const showDebug = useMemo(() => {
    const envEnabled = process.env.NEXT_PUBLIC_SHOW_AUTH_DEBUG === "1";
    if (!router.isReady) {
      return envEnabled;
    }
    const debugParam =
      typeof router.query.debug === "string" ? router.query.debug : "";
    return envEnabled || debugParam === "1";
  }, [router.isReady, router.query.debug]);

  const ensureSession = async () => {
    const { token } = await ensureSessionToken({
      envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
      allowPreviewIssue: true,
    });
    if (token) {
      setSessionToken(token);
    }
    return token;
  };

  const loadMatch = async () => {
    if (!router.isReady || typeof id !== "string") {
      return;
    }

    setLoading(true);
    setError(null);
    setPatient(null);

    const token = getSessionToken() || sessionToken.trim() || (await ensureSession());

    if (!token) {
      setLoading(false);
      setData(null);
      setError(
        "Session is required to view match results. Open /match to start a session, then try again."
      );
      return;
    }

    try {
      const doFetch = async (bearer: string) => {
        return fetch(`${API_BASE}/api/matches/${id}`, {
          headers: { Authorization: `Bearer ${bearer}` },
        });
      };

      let response = await doFetch(token);
      if (response.status === 401) {
        clearSessionToken();
        const refreshed = await ensureSession();
        const nextToken = getSessionToken() || refreshed;
        if (nextToken && nextToken !== token) {
          response = await doFetch(nextToken);
        }
      }

      const payload = (await response.json()) as MatchResponse;
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error?.message || "Failed to load match result");
      }
      setData(payload.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void ensureSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadMatch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady, id, sessionToken]);

  useEffect(() => {
    const patientId = data?.patient_profile_id;
    if (!patientId) {
      return;
    }

    let cancelled = false;
    const loadPatient = async () => {
      const token = getSessionToken() || sessionToken.trim();
      if (!token) {
        return;
      }

      try {
        const response = await fetch(
          `${API_BASE}/api/patients/${encodeURIComponent(patientId)}`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        const payload = (await response.json()) as PatientResponse;
        if (!response.ok || !payload.ok || !payload.data) {
          return;
        }
        if (!cancelled) {
          setPatient(payload.data);
        }
      } catch {
        // Patient context is best-effort. Results should still render.
      }
    };

    void loadPatient();
    return () => {
      cancelled = true;
    };
  }, [data?.patient_profile_id, sessionToken]);

  const tierCounts = useMemo(() => {
    const counts: Record<MatchTier, number> = {
      ELIGIBLE: 0,
      POTENTIAL: 0,
      INELIGIBLE: 0,
    };
    const results = data?.results ?? [];
    for (const item of results) {
      counts[tierFromItem(item)] += 1;
    }
    return counts;
  }, [data]);

  const filters = useMemo(() => {
    return pickFilters(data?.query_json?.filters);
  }, [data]);

  const patientShort = useMemo(() => {
    return shortId(data?.patient_profile_id ?? "");
  }, [data?.patient_profile_id]);

  const patientSummaryText = useMemo(() => {
    const summary = patientSummaryLine(patient);
    if (summary) {
      return summary;
    }
    return patientShort ? `Patient ${patientShort}` : "";
  }, [patient, patientShort]);

  const patientPdfText = useMemo(() => {
    return patientPdfLabel(patient);
  }, [patient]);

  const patientHref = useMemo(() => {
    const idValue = (data?.patient_profile_id ?? "").trim();
    return idValue ? `/patients/${encodeURIComponent(idValue)}` : "/patients";
  }, [data?.patient_profile_id]);

  const groupedResults = useMemo(() => {
    const results = data?.results ?? [];
    const grouped: Record<MatchTier, MatchResultItem[]> = {
      ELIGIBLE: [],
      POTENTIAL: [],
      INELIGIBLE: [],
    };
    for (const item of results) {
      grouped[tierFromItem(item)].push(item);
    }
    return grouped;
  }, [data]);

  const visibleResults = useMemo(() => {
    if (!data) {
      return [];
    }
    const results = data.results;
    if (tierFilter === "ALL") {
      return results;
    }
    return results.filter((item) => tierFromItem(item) === tierFilter);
  }, [data, tierFilter]);

  const renderTrialCard = (item: MatchResultItem) => {
    const tier = tierFromItem(item);
    const counts = computeCounts(item);
    const phaseText = phaseLabel(item.phase);
    const statusText = statusLabel(item.status);
    const isExpanded = Boolean(expandedByTrial[item.nct_id]);
    const showInclusionPass = Boolean(
      showPassBySection[passSectionKey(item.nct_id, "inclusion")]
    );
    const showExclusionPass = Boolean(
      showPassBySection[passSectionKey(item.nct_id, "exclusion")]
    );

    const inclusion = ruleGroups(item.checklist.inclusion);
    const exclusion = ruleGroups(item.checklist.exclusion);

    const toggleExpanded = () =>
      setExpandedByTrial((prev) => ({
        ...prev,
        [item.nct_id]: !isExpanded,
      }));

    const toggleInclusionPass = () =>
      setShowPassBySection((prev) => ({
        ...prev,
        [passSectionKey(item.nct_id, "inclusion")]: !showInclusionPass,
      }));

    const toggleExclusionPass = () =>
      setShowPassBySection((prev) => ({
        ...prev,
        [passSectionKey(item.nct_id, "exclusion")]: !showExclusionPass,
      }));

    const renderRuleItem = (rule: RuleVerdict, key: string) => {
      const metaSummary = summarizeRuleMeta(rule);
      const reasonText = rule.evaluation_meta?.reason?.trim() || "";
      const missingFieldRaw = rule.evaluation_meta?.missing_field?.trim() || "";
      const missingFallback =
        rule.verdict === "UNKNOWN" && item.checklist.missing_info.length > 0
          ? item.checklist.missing_info.join(", ")
          : "";
      const focusValue =
        (missingFieldRaw ||
          (rule.verdict === "UNKNOWN"
            ? item.checklist.missing_info[0] ?? ""
            : "")
        ).trim();
      const patientEditHref =
        rule.verdict === "UNKNOWN" && data?.patient_profile_id
          ? `/patients/${encodeURIComponent(data.patient_profile_id)}/edit${
              focusValue ? `?focus=${encodeURIComponent(focusValue)}` : ""
            }`
          : "";
      const missingText =
        friendlyMissingField(missingFieldRaw) ||
        friendlyMissingField(missingFallback) ||
        missingFallback;
      const whyText =
        reasonText || whyFromReasonCode(rule.evaluation_meta?.reason_code);
      const requiredAction = narrateRequiredAction({
        requiredAction: rule.evaluation_meta?.required_action,
        missingField: missingFieldRaw || missingFallback,
        ruleMeta: rule.rule_meta,
      });
      const debugLine = [
        rule.evaluation_meta?.reason_code
          ? `reason_code=${rule.evaluation_meta.reason_code}`
          : null,
        rule.evaluation_meta?.required_action
          ? `required_action=${rule.evaluation_meta.required_action}`
          : null,
        missingFieldRaw ? `missing_field=${missingFieldRaw}` : null,
      ]
        .filter(Boolean)
        .join(" ");
      return (
        <div key={key} className="result-rule">
          <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
          <div className="result-rule__body">
            <div className="result-rule__summary">{summarizeRule(rule)}</div>
            {metaSummary ? <div className="result-rule__meta">{metaSummary}</div> : null}
            {rule.verdict === "UNKNOWN" ? (
              <div className={styles.unknownCallout}>
                {missingText ? (
                  <div className={styles.unknownRow}>
                    <div className={styles.unknownLabel}>Missing</div>
                    <div className={styles.unknownValue}>{missingText}</div>
                  </div>
                ) : null}
                {whyText ? (
                  <div className={styles.unknownRow}>
                    <div className={styles.unknownLabel}>Why</div>
                    <div className={styles.unknownValue}>{whyText}</div>
                  </div>
                ) : null}
                {requiredAction ? (
                  <div className={styles.unknownRow}>
                    <div className={styles.unknownLabel}>What to collect next</div>
                    <div className={styles.unknownValue}>
                      <div>{requiredAction.title}</div>
                      {requiredAction.detail ? (
                        <div className={styles.unknownDetail}>{requiredAction.detail}</div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                {patientEditHref ? (
                  <div className={styles.unknownRow}>
                    <div className={styles.unknownLabel}>Action</div>
                    <div className={styles.unknownValue}>
                      <Link
                        href={patientEditHref}
                        className="ui-button ui-button--secondary ui-button--sm"
                      >
                        Update patient
                      </Link>
                    </div>
                  </div>
                ) : null}
                {showDebug && debugLine ? (
                  <div className={styles.unknownDebug}>{debugLine}</div>
                ) : null}
              </div>
            ) : reasonText ? (
              <div className="result-rule__missing">{reasonText}</div>
            ) : null}
            <details className="result-rule__evidenceBox">
              <summary>Evidence</summary>
              <div className="result-rule__evidence">
                {rule.evidence || "No evidence excerpt provided."}
              </div>
            </details>
          </div>
        </div>
      );
    };

    const openTrialHref = `/trials/${encodeURIComponent(item.nct_id)}`;

    return (
      <Card key={item.nct_id} className="result-card-v3">
        <div className="result-card-v3__header">
          <div className="result-card-v3__title">
            <div className="result-card-v3__pills">
              <Pill tone={tierTone[tier]}>{tierLabel[tier]}</Pill>
              <Pill tone="warning">{item.nct_id}</Pill>
              {statusText ? <Pill tone={statusTone(item.status)}>{statusText}</Pill> : null}
              {phaseText ? <Pill tone="neutral">{phaseText}</Pill> : null}
            </div>

            <Link href={openTrialHref} className="result-card-v3__link">
              {item.title || item.nct_id}
            </Link>
          </div>

          <div className="result-card-v3__metrics">
            <div className="result-metric">
              <div className="result-metric__label">Score</div>
              <div className="result-metric__value">{item.score.toFixed(2)}</div>
            </div>
            <div className="result-metric">
              <div className="result-metric__label">Certainty</div>
              <div className="result-metric__value">{item.certainty.toFixed(2)}</div>
            </div>
          </div>
        </div>

        <div className="result-card-v3__summary">
          <div className="result-card-v3__counts">
            <Pill tone="success">pass {counts.pass}</Pill>
            <Pill tone="warning">unknown {counts.unknown}</Pill>
            <Pill tone="danger">fail {counts.fail}</Pill>
            <Pill tone="info">missing {counts.missing}</Pill>
          </div>

          <div className="result-card-v3__actions">
            <button
              type="button"
              className="ui-button ui-button--ghost ui-button--sm"
              onClick={toggleExpanded}
            >
              <span className="ui-button__icon" aria-hidden="true">
                <ListChecks size={18} />
              </span>
              {isExpanded ? "Hide details" : "Show details"}
            </button>
            <Link href={openTrialHref} className="ui-button ui-button--secondary ui-button--sm">
              Open trial
              <span className="ui-button__icon" aria-hidden="true">
                <ArrowRight size={18} />
              </span>
            </Link>
          </div>
        </div>

        {isExpanded ? (
          <div className="result-card-v3__details">
            <div className="result-details-grid">
              <Card tone="subtle" className="result-panel">
                <div className="result-panel__header">
                  <div className="result-panel__title">Inclusion</div>
                  <div className="result-panel__meta">
                    <Pill tone="danger">fail {inclusion.FAIL.length}</Pill>
                    <Pill tone="warning">unknown {inclusion.UNKNOWN.length}</Pill>
                  </div>
                </div>

                {inclusion.FAIL.length === 0 && inclusion.UNKNOWN.length === 0 ? (
                  <div className="result-panel__empty">
                    No failed or unknown inclusion checks.
                  </div>
                ) : (
                  <div className="result-rule-list">
                    {inclusion.FAIL.map((rule) =>
                      renderRuleItem(rule, `inc-fail-${item.nct_id}-${rule.rule_id}`)
                    )}
                    {inclusion.UNKNOWN.map((rule) =>
                      renderRuleItem(rule, `inc-unk-${item.nct_id}-${rule.rule_id}`)
                    )}
                  </div>
                )}

                <Accordion
                  open={showInclusionPass}
                  onToggle={toggleInclusionPass}
                  title={
                    <span className="result-pass-toggle">
                      Show PASS ({inclusion.PASS.length})
                    </span>
                  }
                >
                  {inclusion.PASS.length === 0 ? (
                    <div className="result-panel__empty">No passed inclusion checks.</div>
                  ) : (
                    <div className="result-rule-list">
                      {inclusion.PASS.map((rule) =>
                        renderRuleItem(rule, `inc-pass-${item.nct_id}-${rule.rule_id}`)
                      )}
                    </div>
                  )}
                </Accordion>
              </Card>

              <Card tone="subtle" className="result-panel">
                <div className="result-panel__header">
                  <div className="result-panel__title">Exclusion</div>
                  <div className="result-panel__meta">
                    <Pill tone="danger">fail {exclusion.FAIL.length}</Pill>
                    <Pill tone="warning">unknown {exclusion.UNKNOWN.length}</Pill>
                  </div>
                </div>

                {exclusion.FAIL.length === 0 && exclusion.UNKNOWN.length === 0 ? (
                  <div className="result-panel__empty">
                    No failed or unknown exclusion checks.
                  </div>
                ) : (
                  <div className="result-rule-list">
                    {exclusion.FAIL.map((rule) =>
                      renderRuleItem(rule, `exc-fail-${item.nct_id}-${rule.rule_id}`)
                    )}
                    {exclusion.UNKNOWN.map((rule) =>
                      renderRuleItem(rule, `exc-unk-${item.nct_id}-${rule.rule_id}`)
                    )}
                  </div>
                )}

                <Accordion
                  open={showExclusionPass}
                  onToggle={toggleExclusionPass}
                  title={
                    <span className="result-pass-toggle">
                      Show PASS ({exclusion.PASS.length})
                    </span>
                  }
                >
                  {exclusion.PASS.length === 0 ? (
                    <div className="result-panel__empty">No passed exclusion checks.</div>
                  ) : (
                    <div className="result-rule-list">
                      {exclusion.PASS.map((rule) =>
                        renderRuleItem(rule, `exc-pass-${item.nct_id}-${rule.rule_id}`)
                      )}
                    </div>
                  )}
                </Accordion>
              </Card>
            </div>

            <Card tone="subtle" className="result-missing">
              <div className="result-missing__header">
                <span className="result-missing__icon" aria-hidden="true">
                  <AlertTriangle size={18} />
                </span>
                <div className="result-missing__title">Missing info</div>
              </div>
              <div className="result-missing__body">
                {item.checklist.missing_info.length > 0 ? (
                  <div className="result-missing__pills">
                    {item.checklist.missing_info.map((field) => (
                      <Pill key={`${item.nct_id}-${field}`} tone="info">
                        {field}
                      </Pill>
                    ))}
                  </div>
                ) : (
                  <div className="result-panel__empty">No critical missing fields.</div>
                )}
              </div>
            </Card>
          </div>
        ) : null}
      </Card>
    );
  };

  const resultsSummary = useMemo(() => {
    const total = data?.results?.length ?? 0;
    return {
      total,
      eligible: tierCounts.ELIGIBLE,
      potential: tierCounts.POTENTIAL,
      ineligible: tierCounts.INELIGIBLE,
    };
  }, [data, tierCounts]);

  const groupedVisible = useMemo(() => {
    if (!data) {
      return null;
    }

    if (tierFilter === "ALL") {
      return [
        { tier: "ELIGIBLE" as const, items: groupedResults.ELIGIBLE },
        { tier: "POTENTIAL" as const, items: groupedResults.POTENTIAL },
        { tier: "INELIGIBLE" as const, items: groupedResults.INELIGIBLE },
      ];
    }

    return [{ tier: tierFilter as MatchTier, items: visibleResults }];
  }, [data, groupedResults, tierFilter, visibleResults]);

  const isStale = useMemo(() => {
    const updated = patient?.updated_at;
    const created = data?.created_at;
    if (!updated || !created) {
      return false;
    }

    const updatedDate = new Date(updated);
    const createdDate = new Date(created);
    if (Number.isNaN(updatedDate.getTime()) || Number.isNaN(createdDate.getTime())) {
      return false;
    }
    return updatedDate.getTime() > createdDate.getTime();
  }, [data?.created_at, patient?.updated_at]);

  const handleRerunMatch = async () => {
    if (!data || rerunning) {
      return;
    }

    setRerunError(null);
    setRerunning(true);

    const patientProfileId = data.patient_profile_id;
    const topK =
      typeof data.query_json?.top_k === "number" && Number.isFinite(data.query_json.top_k)
        ? data.query_json.top_k
        : 10;
    const filtersObject = data.query_json?.filters ?? {};

    try {
      const result = await withSessionRetry(
        (token) =>
          fetchOk<CreateMatchData>("/api/match", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: {
              patient_profile_id: patientProfileId,
              top_k: topK,
              filters: filtersObject,
            },
          }),
        {
          envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
          allowPreviewIssue: true,
        }
      );
      await router.push(`/matches/${result.match_id}`);
    } catch (err) {
      if (err instanceof Error) {
        setRerunError(err.message);
      } else {
        setRerunError("Unable to rerun match");
      }
    } finally {
      setRerunning(false);
    }
  };

  const handleExportPdf = async () => {
    if (!data) {
      return;
    }
    setExportingPdf(true);
    setExportPdfError(null);
    try {
      await exportMatchPdf({
        match: data,
        filters,
        summary: resultsSummary,
        patientLabel: patientPdfText,
      });
    } catch {
      setExportPdfError(
        "Unable to export PDF right now. Please retry or use Export JSON."
      );
    } finally {
      setExportingPdf(false);
    }
  };

  return (
    <Shell
      className={styles.page}
      kicker="Match results"
      title={typeof id === "string" ? `Match ${id}` : "Match results"}
      subtitle={
        <>
          Review trial-by-trial eligibility evidence. Strong match indicates stronger evidence,
          but still requires clinical confirmation.
        </>
      }
      actions={
        <>
          <Link href="/match" className="ui-button ui-button--secondary ui-button--md">
            New match
            <span className="ui-button__icon" aria-hidden="true">
              <ArrowRight size={18} />
            </span>
          </Link>
          <Link href="/" className="ui-button ui-button--ghost ui-button--md">
            Browse
          </Link>
        </>
      }
    >
      {loading ? (
        <div className="results-skeleton">
          <Card tone="subtle" className="results-hero">
            <div className="results-hero__grid">
              <div>
                <Skeleton width="short" />
                <div style={{ marginTop: 10 }}>
                  <Skeleton width="long" />
                </div>
              </div>
              <div className="results-hero__stats">
                <Skeleton width="short" />
                <Skeleton width="short" />
              </div>
            </div>
          </Card>

          {Array.from({ length: 3 }).map((_, idx) => (
            <Card key={idx} className="result-card-v3">
              <Skeleton width="short" />
              <Skeleton width="long" />
              <Skeleton width="medium" />
            </Card>
          ))}
        </div>
      ) : null}

      {error ? (
        <Toast
          tone="danger"
          title="Unable to load match"
          description={error}
        />
      ) : null}

      {exportPdfError ? (
        <Toast
          tone="warning"
          title="PDF export failed"
          description={exportPdfError}
        />
      ) : null}

      {rerunError ? (
        <Toast tone="danger" title="Unable to rerun match" description={rerunError} />
      ) : null}

      {!loading && data ? (
        <>
          <Card tone="subtle" className="results-hero">
            <div className="results-hero__grid">
              <div className="results-hero__meta">
                <div className="results-hero__metaRow">
                  <span className="results-hero__metaLabel">Patient</span>
                  <span className={styles.patientMetaRight}>
                    <span className={`results-hero__metaValue ${styles.patientSummary}`}>
                      {patientSummaryText}
                    </span>
                    <Link
                      href={patientHref}
                      className={`ui-button ui-button--ghost ui-button--sm ${styles.openPatient}`}
                    >
                      Open patient
                    </Link>
                  </span>
                </div>
                <div className="results-hero__metaRow">
                  <span className="results-hero__metaLabel">Patient ID</span>
                  <span className="results-hero__metaValue">{patientShort}</span>
                </div>
                {showDebug ? (
                  <div className={styles.patientDebug}>
                    patient_profile_id={data.patient_profile_id} match_id={data.id}
                  </div>
                ) : null}
                {isStale ? (
                  <div className={styles.staleHint}>
                    Patient profile updated since this match. Use “Rerun match” to include the
                    latest data.
                  </div>
                ) : null}
                {data.created_at ? (
                  <div className="results-hero__metaRow">
                    <span className="results-hero__metaLabel">Created</span>
                    <span className="results-hero__metaValue">
                      {formatIsoDate(data.created_at)}
                    </span>
                  </div>
                ) : null}
                {typeof data.query_json.top_k === "number" ? (
                  <div className="results-hero__metaRow">
                    <span className="results-hero__metaLabel">Top K</span>
                    <span className="results-hero__metaValue">{data.query_json.top_k}</span>
                  </div>
                ) : null}
                {filters.length > 0 ? (
                  <div className="results-hero__filters">
                    <div className="results-hero__filtersHeader">
                      <Filter size={16} aria-hidden="true" />
                      <span>Filters</span>
                    </div>
                    <div className="results-hero__filtersBody">
                      {filters.map(({ key, value }) => (
                        <Pill key={`${key}-${value}`} tone="brand">
                          {key}: {value}
                        </Pill>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="results-hero__filtersEmpty">
                    <SlidersHorizontal size={16} aria-hidden="true" />
                    No filters applied
                  </div>
                )}
              </div>

              <div className="results-hero__stats">
                <div className="results-stat">
                  <div className="results-stat__value">{resultsSummary.total}</div>
                  <div className="results-stat__label">results</div>
                </div>
                <div className="results-stat">
                  <div className="results-stat__value">{resultsSummary.eligible}</div>
                  <div className="results-stat__label">strong match</div>
                </div>
                <div className="results-stat">
                  <div className="results-stat__value">{resultsSummary.potential}</div>
                  <div className="results-stat__label">potential</div>
                </div>
                <div className="results-stat">
                  <div className="results-stat__value">{resultsSummary.ineligible}</div>
                  <div className="results-stat__label">not eligible</div>
                </div>
              </div>
            </div>

            <div className="results-hero__actions">
              <div className="results-tierTabs">
                <button
                  type="button"
                  className={`results-tierTab ${tierFilter === "ALL" ? "is-active" : ""}`}
                  onClick={() => setTierFilter("ALL")}
                >
                  All <span className="results-tierTab__count">{resultsSummary.total}</span>
                </button>
                <button
                  type="button"
                  className={`results-tierTab ${tierFilter === "ELIGIBLE" ? "is-active" : ""}`}
                  onClick={() => setTierFilter("ELIGIBLE")}
                >
                  Strong match{" "}
                  <span className="results-tierTab__count">{resultsSummary.eligible}</span>
                </button>
                <button
                  type="button"
                  className={`results-tierTab ${tierFilter === "POTENTIAL" ? "is-active" : ""}`}
                  onClick={() => setTierFilter("POTENTIAL")}
                >
                  Potential{" "}
                  <span className="results-tierTab__count">{resultsSummary.potential}</span>
                </button>
                <button
                  type="button"
                  className={`results-tierTab ${tierFilter === "INELIGIBLE" ? "is-active" : ""}`}
                  onClick={() => setTierFilter("INELIGIBLE")}
                >
                  Not eligible{" "}
                  <span className="results-tierTab__count">{resultsSummary.ineligible}</span>
                </button>
              </div>

              <div className="results-hero__buttons">
                <button
                  type="button"
                  className="ui-button ui-button--ghost ui-button--sm"
                  onClick={() => void loadMatch()}
                >
                  <span className="ui-button__icon" aria-hidden="true">
                    <RefreshCcw size={18} />
                  </span>
                  Refresh
                </button>
                <button
                  type="button"
                  className="ui-button ui-button--secondary ui-button--sm"
                  onClick={() => void handleRerunMatch()}
                  disabled={rerunning}
                >
                  <span className="ui-button__icon" aria-hidden="true">
                    <RotateCcw size={18} />
                  </span>
                  {rerunning ? "Rerunning..." : "Rerun match"}
                </button>
                <button
                  type="button"
                  className="ui-button ui-button--secondary ui-button--sm"
                  onClick={() => void handleExportPdf()}
                  disabled={exportingPdf}
                >
                  <span className="ui-button__icon" aria-hidden="true">
                    <Download size={18} />
                  </span>
                  {exportingPdf ? "Exporting PDF..." : "Export PDF"}
                </button>
                <button
                  type="button"
                  className="ui-button ui-button--secondary ui-button--sm"
                  onClick={() => downloadJson(`match-${data.id}.json`, data)}
                >
                  <span className="ui-button__icon" aria-hidden="true">
                    <Download size={18} />
                  </span>
                  Export JSON
                </button>
              </div>
            </div>
          </Card>

          {data.results.length === 0 ? (
            <EmptyState
              title="No results returned"
              description="Try broadening trial filters or running matching again."
              icon={<MapPin size={22} />}
              actions={
                <>
                  <Link href="/match" className="ui-button ui-button--primary ui-button--md">
                    Run another match
                  </Link>
                  <Link href="/" className="ui-button ui-button--secondary ui-button--md">
                    Browse trials
                  </Link>
                </>
              }
            />
          ) : null}

          {data.results.length > 0 ? (
            <div className="results-groups">
              {groupedVisible?.map(({ tier, items }) => {
                if (items.length === 0) {
                  return null;
                }
                return (
                  <section key={tier} className="results-group">
                    {tierFilter === "ALL" ? (
                      <header className="results-group__header">
                        <div className="results-group__titleRow">
                          <Pill tone={tierTone[tier]}>{tierLabel[tier]}</Pill>
                          <div className="results-group__title">
                            {tier === "ELIGIBLE"
                              ? "Strong matches"
                              : tier === "POTENTIAL"
                                ? "Potential matches"
                                : "Not eligible"}
                          </div>
                        </div>
                        <div className="results-group__count">{items.length}</div>
                      </header>
                    ) : null}
                    <div className="results-list">
                      {items.map(renderTrialCard)}
                    </div>
                  </section>
                );
              })}
            </div>
          ) : null}
        </>
      ) : null}

      {!loading && !data && !error ? (
        <EmptyState
          title="Match not available"
          description="This result may have expired or was not found. Run a new match to generate fresh results."
          icon={<ShieldAlert size={22} />}
          actions={
            <>
              <Link href="/match" className="ui-button ui-button--primary ui-button--md">
                New match
              </Link>
              <Link href="/" className="ui-button ui-button--secondary ui-button--md">
                Browse trials
              </Link>
            </>
          }
        />
      ) : null}
    </Shell>
  );
}
