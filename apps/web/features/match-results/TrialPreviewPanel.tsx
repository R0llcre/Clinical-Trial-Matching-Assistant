import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, RefreshCcw } from "lucide-react";

import { Card } from "../../components/ui/Card";
import { Pill } from "../../components/ui/Pill";
import { Skeleton } from "../../components/ui/Skeleton";
import { Tabs } from "../../components/ui/Tabs";
import { ApiError, fetchOk } from "../../lib/http/client";
import styles from "./TrialPreviewPanel.module.css";

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

export function TrialPreviewPanel({ nctId }: { nctId: string }) {
  const [tab, setTab] = useState<"overview" | "eligibility" | "parsed">("overview");
  const [expandedEligibility, setExpandedEligibility] = useState(false);
  const [trial, setTrial] = useState<TrialDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const cacheRef = useRef<Map<string, TrialDetail>>(new Map());

  useEffect(() => {
    setExpandedEligibility(false);
  }, [nctId]);

  useEffect(() => {
    const trimmed = nctId.trim();
    if (!trimmed) {
      setTrial(null);
      setError(null);
      setLoading(false);
      return;
    }

    const cached = cacheRef.current.get(trimmed);
    if (cached) {
      setTrial(cached);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    const run = async () => {
      setLoading(true);
      setError(null);
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
          setError(err.message);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to load trial preview");
        }
        setTrial(null);
      } finally {
        if (!cancelled) {
          setLoading(false);
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

  const statusText = statusLabel(trial?.status);
  const phaseText = phaseLabel(trial?.phase);
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

  return (
    <Card tone="elevated" className={styles.card}>
      <div className={styles.header}>
        <div className={styles.heading}>
          <div className={styles.kicker}>Selected trial</div>
          <div className={styles.title}>{trial?.title || nctId || "Trial preview"}</div>
        </div>
        <Link href={trialHref} className="ui-button ui-button--secondary ui-button--sm">
          Open full trial
          <span className="ui-button__icon" aria-hidden="true">
            <ArrowRight size={18} />
          </span>
        </Link>
      </div>

      {statusText || phaseText || primaryCondition ? (
        <div className={styles.metaRow}>
          {statusText ? <Pill tone="success">{statusText}</Pill> : null}
          {phaseText ? <Pill tone="neutral">{phaseText}</Pill> : null}
          {primaryCondition ? <Pill tone="brand">{primaryCondition}</Pill> : null}
        </div>
      ) : null}

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

      {loading ? (
        <div className={styles.loading}>
          <Skeleton width="long" />
          <Skeleton width="medium" />
          <Skeleton width="short" />
        </div>
      ) : null}

      {error ? (
        <div className={styles.errorBox}>
          <div className={styles.errorTitle}>Unable to load preview</div>
          <div className={styles.errorBody}>{error}</div>
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

      {!loading && !error && trial ? (
        <div className={styles.body}>
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
                    {typeof trial.coverage_stats?.parser_source === "string" &&
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
        </div>
      ) : null}
    </Card>
  );
}

