import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ListChecks, RefreshCcw } from "lucide-react";

import { Card } from "../../components/ui/Card";
import { Pill } from "../../components/ui/Pill";
import { Skeleton } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { ApiError, fetchOk } from "../../lib/http/client";
import { narrateRule } from "../../lib/rules/ruleNarrator";
import {
  friendlyMissingField,
  narrateRequiredAction,
} from "../../lib/rules/requiredActionNarrator";
import styles from "./TrialPreviewPanel.module.css";
import type { MatchResultItem, MatchTier, RuleVerdict } from "./types";

type TrialCriteriaRule = {
  type?: string | null;
  field?: string | null;
  [key: string]: unknown;
};

type TrialDetail = {
  nct_id: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  phase?: string | null;
  conditions?: string[];
  locations?: string[];
  fetched_at?: string | null;
  eligibility_text?: string | null;
  criteria?: TrialCriteriaRule[];
  coverage_stats?: {
    coverage_ratio?: number;
    total_rules?: number;
    known_rules?: number;
    unknown_rules?: number;
    parser_source?: string;
    [key: string]: unknown;
  } | null;
};

const formatIsoDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value.length >= 10 ? value.slice(0, 10) : value;
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

type Props = {
  selectedResult: MatchResultItem | null;
  patientProfileId: string;
  onShowChecklist: () => void;
};

type VerdictCounts = {
  pass: number;
  fail: number;
  unknown: number;
  missing: number;
};

const computeCounts = (item: MatchResultItem): VerdictCounts => {
  const summary = item.match_summary;
  if (summary) {
    return {
      pass: summary.pass,
      fail: summary.fail,
      unknown: summary.unknown,
      missing: summary.missing,
    };
  }
  const allRules = item.checklist.inclusion.concat(item.checklist.exclusion);
  const pass = allRules.filter((rule) => rule.verdict === "PASS").length;
  const fail = allRules.filter((rule) => rule.verdict === "FAIL").length;
  const unknown = allRules.filter((rule) => rule.verdict === "UNKNOWN").length;
  const missing = item.checklist.missing_info.length;
  return { pass, fail, unknown, missing };
};

const tierFromItem = (item: MatchResultItem): MatchTier => {
  const tier = item.match_summary?.tier;
  if (tier === "ELIGIBLE" || tier === "POTENTIAL" || tier === "INELIGIBLE") {
    return tier;
  }
  const counts = computeCounts(item);
  if (counts.fail > 0) {
    return "INELIGIBLE";
  }
  if (counts.unknown > 0 || counts.missing > 0) {
    return "POTENTIAL";
  }
  return "ELIGIBLE";
};

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

const safeText = (value: unknown) =>
  typeof value === "string" ? value.trim() : "";

const keyReasonFallback = (reasonCode?: string | null) => {
  const code = safeText(reasonCode).toUpperCase();
  if (code === "MISSING_FIELD") {
    return "Not enough data in the patient profile to evaluate this criterion.";
  }
  if (code === "NO_EVIDENCE") {
    return "No supporting evidence was found to evaluate this criterion.";
  }
  if (code === "UNSUPPORTED_OPERATOR") {
    return "This criterion uses a rule operator that is not supported yet.";
  }
  return "Not enough data in the patient profile to evaluate this criterion.";
};

export function TrialPreviewPanel({ selectedResult, patientProfileId, onShowChecklist }: Props) {
  const [tab, setTab] = useState<"overview" | "eligibility" | "parsed">("overview");
  const [expandedEligibility, setExpandedEligibility] = useState(false);
  const [trial, setTrial] = useState<TrialDetail | null>(null);
  const [loadingTrial, setLoadingTrial] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const cacheRef = useRef<Map<string, TrialDetail>>(new Map());
  const nctId = safeText(selectedResult?.nct_id);

  useEffect(() => {
    setExpandedEligibility(false);
  }, [nctId]);

  useEffect(() => {
    const trimmed = nctId.trim();
    if (!trimmed) {
      setTrial(null);
      setTrialError(null);
      setLoadingTrial(false);
      return;
    }

    const cached = cacheRef.current.get(trimmed);
    if (cached) {
      setTrial(cached);
      setTrialError(null);
      setLoadingTrial(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    const run = async () => {
      setLoadingTrial(true);
      setTrialError(null);
      try {
        const data = await fetchOk<TrialDetail>(
          `/api/trials/${encodeURIComponent(trimmed)}`,
          { signal: controller.signal }
        );
        if (cancelled) {
          return;
        }
        cacheRef.current.set(trimmed, data);
        setTrial(data);
      } catch (err) {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError) {
          setTrialError(err.message);
        } else if (err instanceof Error) {
          setTrialError(err.message);
        } else {
          setTrialError("Failed to load trial details");
        }
        setTrial(null);
      } finally {
        if (!cancelled) {
          setLoadingTrial(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [nctId, refreshKey]);

  const parsedCriteria = useMemo(() => {
    return Array.isArray(trial?.criteria) ? trial?.criteria ?? [] : [];
  }, [trial?.criteria]);

  const parsedCounts = useMemo(() => {
    let inclusion = 0;
    let exclusion = 0;
    const fieldCounts: Record<string, number> = {};
    for (const rule of parsedCriteria) {
      const type = String(rule.type || "").toUpperCase();
      if (type === "EXCLUSION") {
        exclusion += 1;
      } else {
        inclusion += 1;
      }

      const field = String(rule.field || "").toLowerCase().trim();
      if (field) {
        fieldCounts[field] = (fieldCounts[field] || 0) + 1;
      }
    }

    const topFields = Object.entries(fieldCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);

    return {
      total: parsedCriteria.length,
      inclusion,
      exclusion,
      topFields,
    };
  }, [parsedCriteria]);

  const coverage = useMemo(() => {
    const ratio = trial?.coverage_stats?.coverage_ratio;
    if (typeof ratio === "number" && Number.isFinite(ratio)) {
      return Math.max(0, Math.min(1, ratio));
    }
    return null;
  }, [trial?.coverage_stats?.coverage_ratio]);

  const trialHref = useMemo(() => {
    const trimmed = nctId.trim();
    return trimmed ? `/trials/${encodeURIComponent(trimmed)}` : "/trials";
  }, [nctId]);

  const statusText = statusLabel(selectedResult?.status ?? trial?.status);
  const phaseText = phaseLabel(selectedResult?.phase ?? trial?.phase);
  const fetchedText = formatIsoDate(trial?.fetched_at);
  const conditions = Array.isArray(trial?.conditions) ? trial?.conditions ?? [] : [];
  const primaryCondition = typeof conditions[0] === "string" ? conditions[0] : "";
  const locations = Array.isArray(trial?.locations) ? trial?.locations ?? [] : [];
  const eligibilityTextRaw =
    typeof trial?.eligibility_text === "string" ? trial.eligibility_text.trim() : "";
  const summaryText =
    typeof trial?.summary === "string" ? trial.summary.trim() : "";

  const tabs = useMemo(() => {
    return [
      { id: "overview", label: "Overview" },
      { id: "eligibility", label: "Eligibility" },
      { id: "parsed", label: "Parsed", count: parsedCounts.total },
    ];
  }, [parsedCounts.total]);

  const handleRetry = () => {
    const trimmed = nctId.trim();
    if (trimmed) {
      cacheRef.current.delete(trimmed);
    }
    setRefreshKey((prev) => prev + 1);
  };

  const tier = selectedResult ? tierFromItem(selectedResult) : null;
  const counts = selectedResult ? computeCounts(selectedResult) : null;

  const keyIssues = useMemo(() => {
    if (!selectedResult) {
      return [];
    }
    const inclusion = selectedResult.checklist.inclusion ?? [];
    const exclusion = selectedResult.checklist.exclusion ?? [];
    const exclusionFail = exclusion.filter((rule) => rule.verdict === "FAIL");
    const inclusionFail = inclusion.filter((rule) => rule.verdict === "FAIL");
    const exclusionUnknown = exclusion.filter((rule) => rule.verdict === "UNKNOWN");
    const inclusionUnknown = inclusion.filter((rule) => rule.verdict === "UNKNOWN");
    return [
      ...exclusionFail,
      ...inclusionFail,
      ...exclusionUnknown,
      ...inclusionUnknown,
    ];
  }, [selectedResult]);

  const topIssues = useMemo(() => keyIssues.slice(0, 4), [keyIssues]);

  const keyChecks = useMemo(() => {
    if (!selectedResult) {
      return [];
    }
    const inclusion = selectedResult.checklist.inclusion ?? [];
    const exclusion = selectedResult.checklist.exclusion ?? [];
    const passRules = [...inclusion, ...exclusion].filter((rule) => rule.verdict === "PASS");
    return passRules.slice(0, 3);
  }, [selectedResult]);

  const patientIdValue = safeText(patientProfileId);
  const buildUpdatePatientHref = (focus?: string) => {
    const base = patientIdValue ? `/patients/${encodeURIComponent(patientIdValue)}/edit` : "/patients";
    const focusValue = safeText(focus);
    if (!patientIdValue) {
      return base;
    }
    if (!focusValue) {
      return base;
    }
    return `${base}?focus=${encodeURIComponent(focusValue)}`;
  };

  const renderRuleLine = (rule: RuleVerdict) => {
    const meta = rule.rule_meta;
    if (meta) {
      const rawValue = meta.value;
      const value =
        typeof rawValue === "string" ||
        typeof rawValue === "number" ||
        Array.isArray(rawValue)
          ? rawValue
          : null;
      return narrateRule({ ...meta, value });
    }
    const evidence = safeText(rule.evidence);
    return evidence || "Criterion";
  };

  const renderUnknownCallout = (rule: RuleVerdict) => {
    const missingRaw =
      safeText(rule.evaluation_meta?.missing_field) ||
      (selectedResult?.checklist.missing_info?.[0] ?? "");
    const missingPretty = friendlyMissingField(missingRaw);
    const reason =
      safeText(rule.evaluation_meta?.reason) ||
      keyReasonFallback(rule.evaluation_meta?.reason_code);
    const action = narrateRequiredAction({
      requiredAction: rule.evaluation_meta?.required_action,
      missingField: missingRaw,
      ruleMeta: rule.rule_meta,
    });

    return (
      <div className={styles.unknownCallout}>
        {missingPretty || missingRaw ? (
          <div className={styles.calloutRow}>
            <div className={styles.calloutLabel}>Missing</div>
            <div className={styles.calloutValue}>{missingPretty || missingRaw}</div>
          </div>
        ) : null}

        <div className={styles.calloutRow}>
          <div className={styles.calloutLabel}>Why</div>
          <div className={styles.calloutValue}>{reason}</div>
        </div>

        {action ? (
          <div className={styles.calloutRow}>
            <div className={styles.calloutLabel}>What to collect next</div>
            <div className={styles.calloutValue}>
              <div>{action.title}</div>
              {action.detail ? <div className={styles.calloutDetail}>{action.detail}</div> : null}
            </div>
          </div>
        ) : null}

        {patientIdValue ? (
          <div className={styles.calloutActions}>
            <Link href={buildUpdatePatientHref(missingRaw)} className="ui-button ui-button--secondary ui-button--sm">
              Update patient
            </Link>
          </div>
        ) : null}
      </div>
    );
  };

  const renderIssueItem = (rule: RuleVerdict, index: number) => {
    const verdictTone =
      rule.verdict === "FAIL" ? "danger" : rule.verdict === "UNKNOWN" ? "warning" : "success";
    const isUnknown = rule.verdict === "UNKNOWN";
    const reasonText = safeText(rule.evaluation_meta?.reason);

    return (
      <div key={`${rule.rule_id}-${index}`} className={styles.issueItem}>
        <div className={styles.issueHeader}>
          <Pill tone={verdictTone}>{rule.verdict}</Pill>
          <div className={styles.issueTitle}>{renderRuleLine(rule)}</div>
        </div>
        {rule.verdict === "FAIL" && reasonText ? (
          <div className={styles.issueReason}>{reasonText}</div>
        ) : null}
        {isUnknown ? renderUnknownCallout(rule) : null}
      </div>
    );
  };

  return (
    <Card tone="elevated" className={styles.card}>
      <div className={styles.header}>
        <div className={styles.heading}>
          <div className={styles.kicker}>Trial preview</div>
          <div className={styles.hint}>
            Click a result card to preview. This does not change ranking.
          </div>
          <div className={styles.title}>
            {safeText(selectedResult?.title) || nctId || "Trial preview"}
          </div>
        </div>
        {nctId ? (
          <Link href={trialHref} className="ui-button ui-button--secondary ui-button--sm">
            Open full trial
            <span className="ui-button__icon" aria-hidden="true">
              <ArrowRight size={18} />
            </span>
          </Link>
        ) : null}
      </div>

      {statusText || phaseText || primaryCondition || nctId ? (
        <div className={styles.metaRow}>
          {tier ? <Pill tone={tierTone[tier]}>{tierLabel[tier]}</Pill> : null}
          {nctId ? <Pill tone="warning">{nctId}</Pill> : null}
          {statusText ? <Pill tone="success">{statusText}</Pill> : null}
          {phaseText ? <Pill tone="neutral">{phaseText}</Pill> : null}
          {primaryCondition ? <Pill tone="brand">{primaryCondition}</Pill> : null}
        </div>
      ) : null}

      {selectedResult && counts ? (
        <div className={styles.snapshot}>
          <div className={styles.snapshotHeader}>
            <div className={styles.snapshotTitle}>Match snapshot</div>
            <button
              type="button"
              className="ui-button ui-button--ghost ui-button--sm"
              onClick={onShowChecklist}
            >
              <span className="ui-button__icon" aria-hidden="true">
                <ListChecks size={18} />
              </span>
              Show full checklist
            </button>
          </div>

          <div className={styles.snapshotMetrics}>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>Score</div>
              <div className={styles.metricValue}>{selectedResult.score.toFixed(2)}</div>
            </div>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>Certainty</div>
              <div className={styles.metricValue}>{selectedResult.certainty.toFixed(2)}</div>
            </div>
          </div>

          <div className={styles.snapshotCounts}>
            <Pill tone="success">pass {counts.pass}</Pill>
            <Pill tone="warning">unknown {counts.unknown}</Pill>
            <Pill tone="danger">fail {counts.fail}</Pill>
            <Pill tone="info">missing {counts.missing}</Pill>
          </div>
        </div>
      ) : null}

      {selectedResult ? (
        <div className={styles.issues}>
          {topIssues.length > 0 ? (
            <>
              <div className={styles.sectionTitle}>Key issues</div>
              <div className={styles.issuesList}>
                {topIssues.map((rule, idx) => renderIssueItem(rule, idx))}
              </div>
            </>
          ) : (
            <>
              <div className={styles.sectionTitle}>Key checks</div>
              <div className={styles.okBox}>
                <div className={styles.okTitle}>
                  All checks passed (based on available data).
                </div>
                {keyChecks.length > 0 ? (
                  <ul className={styles.okList}>
                    {keyChecks.map((rule) => (
                      <li key={rule.rule_id}>{renderRuleLine(rule)}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </>
          )}
        </div>
      ) : (
        <div className={styles.placeholder}>
          Select a trial result to preview details and key issues.
        </div>
      )}

      {fetchedText || locations.length > 0 ? (
        <div className={styles.smallMeta}>
          {fetchedText ? <span>Last sync: {fetchedText}</span> : null}
          {fetchedText && locations.length > 0 ? <span className={styles.dot}>•</span> : null}
          {locations.length > 0 ? <span>Locations: {locations.length}</span> : null}
        </div>
      ) : null}

      <Tabs
        items={tabs}
        activeId={tab}
        onChange={(next) => setTab(next as typeof tab)}
        ariaLabel="Trial preview tabs"
      />

      <div className={styles.body}>
        {loadingTrial ? (
          <div className={styles.loading}>
            <Skeleton width="long" />
            <Skeleton width="medium" />
            <Skeleton width="short" />
          </div>
        ) : null}

        {!loadingTrial && trialError ? (
          <div className={styles.inlineError}>
            <div className={styles.inlineErrorTitle}>Trial details unavailable</div>
            <div className={styles.inlineErrorBody}>{trialError}</div>
            <button
              type="button"
              className="ui-button ui-button--secondary ui-button--sm"
              onClick={handleRetry}
            >
              <span className="ui-button__icon" aria-hidden="true">
                <RefreshCcw size={18} />
              </span>
              Retry
            </button>
          </div>
        ) : null}

        {!loadingTrial && !trialError ? (
          <>
            {tab === "overview" ? (
              <div className={styles.section}>
                {summaryText ? (
                  <div className={styles.summary}>{summaryText}</div>
                ) : (
                  <div className={styles.placeholder}>No summary available.</div>
                )}
              </div>
            ) : null}

            {tab === "eligibility" ? (
              <div className={styles.section}>
                {eligibilityTextRaw ? (
                  <>
                    <div
                      className={`${styles.eligibilityText} ${
                        expandedEligibility ? "" : styles.eligibilityCollapsed
                      }`}
                    >
                      {eligibilityTextRaw}
                    </div>
                    <button
                      type="button"
                      className="ui-button ui-button--ghost ui-button--sm"
                      onClick={() => setExpandedEligibility((prev) => !prev)}
                    >
                      {expandedEligibility ? "Collapse" : "Show full eligibility"}
                    </button>
                  </>
                ) : (
                  <div className={styles.placeholder}>
                    No eligibility text available for this trial.
                  </div>
                )}
              </div>
            ) : null}

            {tab === "parsed" ? (
              <div className={styles.section}>
                {parsedCounts.total > 0 ? (
                  <>
                    <div className={styles.parsedStats}>
                      <div className={styles.statRow}>
                        <span className={styles.statLabel}>Rules</span>
                        <span className={styles.statValue}>{parsedCounts.total}</span>
                      </div>
                      <div className={styles.statRow}>
                        <span className={styles.statLabel}>Inclusion</span>
                        <span className={styles.statValue}>{parsedCounts.inclusion}</span>
                      </div>
                      <div className={styles.statRow}>
                        <span className={styles.statLabel}>Exclusion</span>
                        <span className={styles.statValue}>{parsedCounts.exclusion}</span>
                      </div>
                      {coverage !== null ? (
                        <div className={styles.statRow}>
                          <span className={styles.statLabel}>Coverage</span>
                          <span className={styles.statValue}>
                            {Math.round(coverage * 100)}%
                          </span>
                        </div>
                      ) : null}
                      {typeof trial?.coverage_stats?.parser_source === "string" &&
                      trial.coverage_stats.parser_source.trim() ? (
                        <div className={styles.statRow}>
                          <span className={styles.statLabel}>Parser</span>
                          <span className={styles.statValue}>
                            {trial.coverage_stats.parser_source}
                          </span>
                        </div>
                      ) : null}
                    </div>

                    {parsedCounts.topFields.length > 0 ? (
                      <div className={styles.fieldPills}>
                        {parsedCounts.topFields.map(([field, count]) => (
                          <Pill key={field} tone="neutral">
                            {field} {count}
                          </Pill>
                        ))}
                      </div>
                    ) : null}

                    <div className={styles.parsedHint}>
                      For full parsed criteria, open the trial detail page.
                    </div>
                  </>
                ) : (
                  <div className={styles.placeholder}>
                    No parsed criteria available yet for this trial.
                  </div>
                )}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </Card>
  );
}
