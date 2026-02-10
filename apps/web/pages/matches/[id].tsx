import Link from "next/link";
import { useRouter } from "next/router";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Download,
  Filter,
  ListChecks,
  MapPin,
  RefreshCcw,
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

type RuleVerdict = {
  rule_id: string;
  verdict: "PASS" | "FAIL" | "UNKNOWN";
  evidence: string;
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const SESSION_KEY = "ctmatch.jwt";

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

const verdictTone: Record<
  RuleVerdict["verdict"],
  "success" | "warning" | "danger"
> = {
  PASS: "success",
  FAIL: "danger",
  UNKNOWN: "warning",
};

const ruleBadgeLabel = (rule: RuleVerdict): ReactNode => {
  if (!rule.rule_id) {
    return null;
  }
  return <span className="rule-id">{rule.rule_id}</span>;
};

export default function MatchResultsPage() {
  const router = useRouter();
  const { id } = router.query;

  const [sessionToken, setSessionToken] = useState(
    process.env.NEXT_PUBLIC_DEV_JWT ?? ""
  );
  const [data, setData] = useState<MatchData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedByTrial, setExpandedByTrial] = useState<Record<string, boolean>>(
    {}
  );
  const [showPassByTrial, setShowPassByTrial] = useState<Record<string, boolean>>(
    {}
  );
  const [tierFilter, setTierFilter] = useState<TierFilter>("ALL");

  const ensureSession = async () => {
    const saved = window.localStorage.getItem(SESSION_KEY)?.trim() ?? "";
    if (saved) {
      setSessionToken(saved);
      return saved;
    }

    const envToken = (process.env.NEXT_PUBLIC_DEV_JWT ?? "").trim();
    if (envToken) {
      window.localStorage.setItem(SESSION_KEY, envToken);
      setSessionToken(envToken);
      return envToken;
    }

    try {
      const response = await fetch(`${API_BASE}/api/auth/preview-token`);
      if (!response.ok) {
        return "";
      }
      const payload = (await response.json()) as {
        ok: boolean;
        data?: { token?: string };
      };
      const token = payload.data?.token?.trim() ?? "";
      if (payload.ok && token) {
        window.localStorage.setItem(SESSION_KEY, token);
        setSessionToken(token);
        return token;
      }
      return "";
    } catch {
      return "";
    }
  };

  const loadMatch = async () => {
    if (!router.isReady || typeof id !== "string") {
      return;
    }

    setLoading(true);
    setError(null);

    const token =
      (window.localStorage.getItem(SESSION_KEY) ?? sessionToken).trim() ||
      (await ensureSession());

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
        window.localStorage.removeItem(SESSION_KEY);
        const refreshed = await ensureSession();
        const nextToken = (window.localStorage.getItem(SESSION_KEY) ?? refreshed).trim();
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
    const showPass = Boolean(showPassByTrial[item.nct_id]);

    const inclusion = ruleGroups(item.checklist.inclusion);
    const exclusion = ruleGroups(item.checklist.exclusion);

    const toggleExpanded = () =>
      setExpandedByTrial((prev) => ({
        ...prev,
        [item.nct_id]: !isExpanded,
      }));

    const toggleShowPass = () =>
      setShowPassByTrial((prev) => ({
        ...prev,
        [item.nct_id]: !showPass,
      }));

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
                    {inclusion.FAIL.map((rule) => (
                      <div key={`inc-fail-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                        <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                        <div className="result-rule__body">
                          <div className="result-rule__evidence">{rule.evidence}</div>
                          {ruleBadgeLabel(rule)}
                        </div>
                      </div>
                    ))}
                    {inclusion.UNKNOWN.map((rule) => (
                      <div key={`inc-unk-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                        <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                        <div className="result-rule__body">
                          <div className="result-rule__evidence">{rule.evidence}</div>
                          {ruleBadgeLabel(rule)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Accordion
                  open={showPass}
                  onToggle={toggleShowPass}
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
                      {inclusion.PASS.map((rule) => (
                        <div key={`inc-pass-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                          <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                          <div className="result-rule__body">
                            <div className="result-rule__evidence">{rule.evidence}</div>
                            {ruleBadgeLabel(rule)}
                          </div>
                        </div>
                      ))}
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
                    {exclusion.FAIL.map((rule) => (
                      <div key={`exc-fail-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                        <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                        <div className="result-rule__body">
                          <div className="result-rule__evidence">{rule.evidence}</div>
                          {ruleBadgeLabel(rule)}
                        </div>
                      </div>
                    ))}
                    {exclusion.UNKNOWN.map((rule) => (
                      <div key={`exc-unk-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                        <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                        <div className="result-rule__body">
                          <div className="result-rule__evidence">{rule.evidence}</div>
                          {ruleBadgeLabel(rule)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Accordion
                  open={showPass}
                  onToggle={toggleShowPass}
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
                      {exclusion.PASS.map((rule) => (
                        <div key={`exc-pass-${item.nct_id}-${rule.rule_id}`} className="result-rule">
                          <Pill tone={verdictTone[rule.verdict]}>{rule.verdict}</Pill>
                          <div className="result-rule__body">
                            <div className="result-rule__evidence">{rule.evidence}</div>
                            {ruleBadgeLabel(rule)}
                          </div>
                        </div>
                      ))}
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

  return (
    <Shell
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

      {!loading && data ? (
        <>
          <Card tone="subtle" className="results-hero">
            <div className="results-hero__grid">
              <div className="results-hero__meta">
                <div className="results-hero__metaRow">
                  <span className="results-hero__metaLabel">Patient profile</span>
                  <span className="results-hero__metaValue">{data.patient_profile_id}</span>
                </div>
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
