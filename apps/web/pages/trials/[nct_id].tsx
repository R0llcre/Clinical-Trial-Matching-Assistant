import Link from "next/link";
import type { GetServerSideProps } from "next";
import { useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  FileText,
  Globe,
  Info,
  ListChecks,
  MapPin,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Accordion } from "../../components/ui/Accordion";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Pill } from "../../components/ui/Pill";
import type { TabItem } from "../../components/ui/Tabs";
import { Tabs } from "../../components/ui/Tabs";
import { Toast } from "../../components/ui/Toast";

type TrialDetail = {
  nct_id: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  phase?: string | null;
  conditions: string[];
  eligibility_text?: string | null;
  criteria?: ParsedRule[];
  criteria_parser_version?: string | null;
  coverage_stats?: {
    total_rules?: number;
    known_rules?: number;
    unknown_rules?: number;
    failed_rules?: number;
    coverage_ratio?: number;
  } | null;
  locations: string[];
  fetched_at?: string | null;
};

type ParsedRule = {
  id: string;
  type: "INCLUSION" | "EXCLUSION";
  field: string;
  operator: string;
  value: string | number | null;
  unit?: string | null;
  certainty?: string | null;
  evidence_text: string;
};

type TrialResponse = {
  ok: boolean;
  data?: TrialDetail;
  error?: {
    code: string;
    message: string;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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

const formatFetchedDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value.length >= 10 ? value.slice(0, 10) : value;
};

const formatRuleExpression = (rule: ParsedRule) => {
  const pieces = [rule.field, rule.operator].filter(Boolean);
  const value =
    rule.value === null || rule.value === undefined ? "" : String(rule.value);
  if (value) {
    pieces.push(value);
  }
  if (rule.unit) {
    pieces.push(rule.unit);
  }
  const base = pieces.join(" ").replace(/\s+/g, " ").trim();
  return base || "Rule";
};

type TrialDetailPageProps = {
  trial: TrialDetail | null;
  error: string | null;
};

export const getServerSideProps: GetServerSideProps<TrialDetailPageProps> = async (
  ctx
) => {
  const nctId =
    typeof ctx.params?.nct_id === "string" ? ctx.params.nct_id : null;
  if (!nctId) {
    return { props: { trial: null, error: "Missing nct_id" } };
  }

  try {
    const response = await fetch(`${API_BASE}/api/trials/${encodeURIComponent(nctId)}`);
    const payload = (await response.json()) as TrialResponse;
    if (!response.ok || !payload.ok) {
      return {
        props: {
          trial: null,
          error: payload.error?.message || "Failed to load trial",
        },
      };
    }
    return { props: { trial: payload.data ?? null, error: null } };
  } catch {
    return { props: { trial: null, error: "Failed to load trial" } };
  }
};

export default function TrialDetailPage(props: TrialDetailPageProps) {
  const trial = props.trial;
  const error = props.error;
  const [activeTab, setActiveTab] = useState<"overview" | "eligibility" | "parsed">(
    "overview"
  );
  const [eligibilityExpanded, setEligibilityExpanded] = useState(false);
  const [openRules, setOpenRules] = useState<Record<string, boolean>>({});

  const eligibilityText = trial?.eligibility_text ?? "";
  const eligibilityLines = eligibilityText ? eligibilityText.split("\n") : [];
  const eligibilityPreview = eligibilityLines.slice(0, 20).join("\n");
  const eligibilityTruncated = eligibilityLines.length > 20;
  const eligibilityShown =
    eligibilityTruncated && !eligibilityExpanded
      ? `${eligibilityPreview}\n\n…`
      : eligibilityText || "No eligibility text provided.";

  const inclusionRules =
    trial?.criteria?.filter((rule) => rule.type === "INCLUSION") ?? [];
  const exclusionRules =
    trial?.criteria?.filter((rule) => rule.type === "EXCLUSION") ?? [];

  const clinicalTrialsHref = trial?.nct_id
    ? `https://clinicaltrials.gov/study/${encodeURIComponent(trial.nct_id)}`
    : "https://clinicaltrials.gov/";

  const tabItems: TabItem[] = useMemo(() => {
    return [
      { id: "overview", label: "Overview" },
      { id: "eligibility", label: "Eligibility" },
      {
        id: "parsed",
        label: "Parsed criteria",
        count: trial?.criteria?.length ?? 0,
        disabled: !trial,
      },
    ];
  }, [trial]);

  const summaryText = trial?.summary?.trim();
  const summaryShown = summaryText
    ? summaryText
    : "Summary unavailable. Review eligibility criteria for details.";

  const phaseText = phaseLabel(trial?.phase);
  const statusText = statusLabel(trial?.status);

  const conditionsShown = (trial?.conditions ?? []).slice(0, 8);
  const conditionsRemaining = (trial?.conditions?.length ?? 0) - conditionsShown.length;

  const locationsShown = (trial?.locations ?? []).slice(0, 10);
  const locationsRemaining = (trial?.locations?.length ?? 0) - locationsShown.length;

  return (
    <Shell
      kicker={trial?.nct_id ?? "Trial"}
      title={trial?.title ?? "Trial details"}
      subtitle={
        <>
          Review official eligibility text and extracted criteria. Always confirm with the
          study record and your care team.
        </>
      }
      actions={
        <>
          <Link href="/" className="ui-button ui-button--ghost ui-button--md">
            Back to browse
          </Link>
          <Link
            href={{
              pathname: "/match",
              query: trial?.conditions?.[0] ? { condition: trial.conditions[0] } : undefined,
            }}
            className="ui-button ui-button--primary ui-button--md"
          >
            Match a patient
            <span className="ui-button__icon" aria-hidden="true">
              <ArrowRight size={18} />
            </span>
          </Link>
        </>
      }
    >
      {error ? (
        <Toast
          tone="danger"
          title="Unable to load trial"
          description={error}
          className="trial-toast"
        />
      ) : null}

      {!trial ? (
        <EmptyState
          title="Trial not available"
          description="The record may not be synced yet, or the NCT ID is invalid. Try browsing the dataset and opening a trial from the list."
          icon={<ShieldAlert size={22} />}
          actions={
            <>
              <Link href="/" className="ui-button ui-button--primary ui-button--md">
                Browse trials
              </Link>
              <a
                href={clinicalTrialsHref}
                className="ui-button ui-button--secondary ui-button--md"
                target="_blank"
                rel="noreferrer"
              >
                Open ClinicalTrials.gov
                <span className="ui-button__icon" aria-hidden="true">
                  <Globe size={18} />
                </span>
              </a>
            </>
          }
        />
      ) : (
        <div className="trial-detail-layout">
          <section className="trial-detail-main">
            <Card tone="subtle" className="trial-detail-hero">
              <div className="trial-detail-hero__meta">
                <div className="trial-detail-hero__pills">
                  {statusText ? <Pill tone={statusTone(trial.status)}>{statusText}</Pill> : null}
                  {phaseText ? <Pill tone="neutral">{phaseText}</Pill> : null}
                  {trial.fetched_at ? (
                    <Pill tone="brand">
                      <span className="trial-pill-icon" aria-hidden="true">
                        <CalendarClock size={14} />
                      </span>
                      Synced {formatFetchedDate(trial.fetched_at)}
                    </Pill>
                  ) : null}
                </div>
                <a
                  className="trial-detail-hero__external"
                  href={clinicalTrialsHref}
                  target="_blank"
                  rel="noreferrer"
                >
                  Official record
                  <span className="trial-pill-icon" aria-hidden="true">
                    <Globe size={16} />
                  </span>
                </a>
              </div>

              <Tabs
                items={tabItems}
                activeId={activeTab}
                onChange={(value) => setActiveTab(value as typeof activeTab)}
                ariaLabel="Trial sections"
              />
            </Card>

            {activeTab === "overview" ? (
              <section role="tabpanel" aria-label="Overview" className="trial-panel">
                <Card className="trial-section">
                  <div className="trial-section__header">
                    <span className="trial-section__icon" aria-hidden="true">
                      <Info size={18} />
                    </span>
                    <h2 className="trial-section__title">Summary</h2>
                  </div>
                  <div className="trial-prose">{summaryShown}</div>
                </Card>

                <Card className="trial-section trial-section--callout">
                  <div className="trial-callout">
                    <div className="trial-callout__icon" aria-hidden="true">
                      <CheckCircle2 size={18} />
                    </div>
                    <div className="trial-callout__body">
                      <div className="trial-callout__title">Next step</div>
                      <div className="trial-callout__desc">
                        Use matching to generate an eligibility checklist, then confirm with the official record.
                      </div>
                    </div>
                    <Link
                      href={{
                        pathname: "/match",
                        query: trial.conditions?.[0]
                          ? { condition: trial.conditions[0] }
                          : undefined,
                      }}
                      className="ui-button ui-button--secondary ui-button--md"
                    >
                      Try matching
                      <span className="ui-button__icon" aria-hidden="true">
                        <ArrowRight size={18} />
                      </span>
                    </Link>
                  </div>
                </Card>
              </section>
            ) : null}

            {activeTab === "eligibility" ? (
              <section role="tabpanel" aria-label="Eligibility" className="trial-panel">
                <Card className="trial-section">
                  <div className="trial-section__header">
                    <span className="trial-section__icon" aria-hidden="true">
                      <FileText size={18} />
                    </span>
                    <h2 className="trial-section__title">Eligibility criteria</h2>
                  </div>
                  <div className="trial-prose trial-prose--preline">{eligibilityShown}</div>
                  {eligibilityTruncated ? (
                    <button
                      type="button"
                      className="ui-button ui-button--ghost ui-button--sm trial-expand"
                      onClick={() => setEligibilityExpanded((value) => !value)}
                    >
                      {eligibilityExpanded ? "Collapse" : "Show full eligibility"}
                    </button>
                  ) : null}
                </Card>
              </section>
            ) : null}

            {activeTab === "parsed" ? (
              <section role="tabpanel" aria-label="Parsed criteria" className="trial-panel">
                <Card className="trial-section">
                  <div className="trial-section__header">
                    <span className="trial-section__icon" aria-hidden="true">
                      <ListChecks size={18} />
                    </span>
                    <h2 className="trial-section__title">Parsed criteria</h2>
                  </div>

                  <div className="trial-coverage">
                    {trial.criteria_parser_version ? (
                      <Pill tone="warning">{trial.criteria_parser_version}</Pill>
                    ) : (
                      <Pill tone="neutral">Parser unavailable</Pill>
                    )}
                    {trial.coverage_stats?.coverage_ratio !== undefined ? (
                      <Pill tone="brand">
                        coverage {(trial.coverage_stats.coverage_ratio * 100).toFixed(0)}%
                      </Pill>
                    ) : null}
                    {trial.coverage_stats?.total_rules !== undefined ? (
                      <Pill tone="neutral">rules {trial.coverage_stats.total_rules}</Pill>
                    ) : null}
                    {trial.coverage_stats?.unknown_rules !== undefined ? (
                      <Pill tone="info">unknown {trial.coverage_stats.unknown_rules}</Pill>
                    ) : null}
                  </div>

                  {trial.criteria && trial.criteria.length > 0 ? (
                    <div className="trial-rules">
                      <div className="trial-rules__section">
                        <div className="trial-rules__heading">
                          <div className="trial-rules__title">Inclusion</div>
                          <div className="trial-rules__count">{inclusionRules.length}</div>
                        </div>
                        <div className="trial-rules__list">
                          {inclusionRules.length === 0 ? (
                            <div className="trial-rules__empty">
                              <XCircle size={18} aria-hidden="true" />
                              No inclusion rules extracted.
                            </div>
                          ) : (
                            inclusionRules.map((rule) => (
                              <Accordion
                                key={rule.id}
                                open={Boolean(openRules[rule.id])}
                                onToggle={() =>
                                  setOpenRules((prev) => ({
                                    ...prev,
                                    [rule.id]: !prev[rule.id],
                                  }))
                                }
                                title={
                                  <div className="trial-rule-title">
                                    <div className="trial-rule-title__expr">
                                      {formatRuleExpression(rule)}
                                    </div>
                                    <div className="trial-rule-title__meta">
                                      <Pill tone="success">Inclusion</Pill>
                                      <Pill tone="brand">{rule.field}</Pill>
                                    </div>
                                  </div>
                                }
                              >
                                <div className="trial-rule-body">
                                  <div className="trial-rule-body__label">Evidence</div>
                                  <div className="trial-rule-body__text">
                                    {rule.evidence_text}
                                  </div>
                                </div>
                              </Accordion>
                            ))
                          )}
                        </div>
                      </div>

                      <div className="trial-rules__section">
                        <div className="trial-rules__heading">
                          <div className="trial-rules__title">Exclusion</div>
                          <div className="trial-rules__count">{exclusionRules.length}</div>
                        </div>
                        <div className="trial-rules__list">
                          {exclusionRules.length === 0 ? (
                            <div className="trial-rules__empty">
                              <CheckCircle2 size={18} aria-hidden="true" />
                              No exclusion rules extracted.
                            </div>
                          ) : (
                            exclusionRules.map((rule) => (
                              <Accordion
                                key={rule.id}
                                open={Boolean(openRules[rule.id])}
                                onToggle={() =>
                                  setOpenRules((prev) => ({
                                    ...prev,
                                    [rule.id]: !prev[rule.id],
                                  }))
                                }
                                title={
                                  <div className="trial-rule-title">
                                    <div className="trial-rule-title__expr">
                                      {formatRuleExpression(rule)}
                                    </div>
                                    <div className="trial-rule-title__meta">
                                      <Pill tone="danger">Exclusion</Pill>
                                      <Pill tone="brand">{rule.field}</Pill>
                                    </div>
                                  </div>
                                }
                              >
                                <div className="trial-rule-body">
                                  <div className="trial-rule-body__label">Evidence</div>
                                  <div className="trial-rule-body__text">
                                    {rule.evidence_text}
                                  </div>
                                </div>
                              </Accordion>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <EmptyState
                      title="No parsed criteria available"
                      description="This preview may not have run the parser for this record yet. You can still review the official eligibility text above."
                      icon={<BookOpen size={22} />}
                    />
                  )}
                </Card>
              </section>
            ) : null}
          </section>

          <aside className="trial-detail-aside">
            <Card className="trial-aside-card">
              <div className="trial-aside-card__title">Quick facts</div>
              <div className="trial-aside-facts">
                <div className="trial-aside-fact">
                  <span className="trial-aside-fact__label">NCT ID</span>
                  <span className="trial-aside-fact__value">{trial.nct_id}</span>
                </div>
                {statusText ? (
                  <div className="trial-aside-fact">
                    <span className="trial-aside-fact__label">Status</span>
                    <span className="trial-aside-fact__value">{statusText}</span>
                  </div>
                ) : null}
                {phaseText ? (
                  <div className="trial-aside-fact">
                    <span className="trial-aside-fact__label">Phase</span>
                    <span className="trial-aside-fact__value">{phaseText}</span>
                  </div>
                ) : null}
                {trial.criteria_parser_version ? (
                  <div className="trial-aside-fact">
                    <span className="trial-aside-fact__label">Parser</span>
                    <span className="trial-aside-fact__value">
                      {trial.criteria_parser_version}
                    </span>
                  </div>
                ) : null}
              </div>
              <div className="trial-aside-actions">
                <Link href="/" className="ui-button ui-button--ghost ui-button--md">
                  Browse
                </Link>
                <Link
                  href={{
                    pathname: "/match",
                    query: trial.conditions?.[0]
                      ? { condition: trial.conditions[0] }
                      : undefined,
                  }}
                  className="ui-button ui-button--primary ui-button--md"
                >
                  Use in match
                  <span className="ui-button__icon" aria-hidden="true">
                    <ArrowRight size={18} />
                  </span>
                </Link>
              </div>
            </Card>

            <Card className="trial-aside-card" tone="subtle">
              <div className="trial-aside-card__title">Conditions</div>
              <div className="trial-aside-pills">
                {conditionsShown.length > 0 ? (
                  conditionsShown.map((value) => (
                    <Pill key={value} tone="neutral">
                      {value}
                    </Pill>
                  ))
                ) : (
                  <div className="trial-aside-muted">Condition data pending.</div>
                )}
                {conditionsRemaining > 0 ? (
                  <Pill tone="info">+{conditionsRemaining} more</Pill>
                ) : null}
              </div>
            </Card>

            <Card className="trial-aside-card" tone="subtle">
              <div className="trial-aside-card__title">Locations</div>
              {locationsShown.length > 0 ? (
                <ul className="trial-location-list">
                  {locationsShown.map((location) => (
                    <li key={location}>
                      <MapPin size={16} aria-hidden="true" />
                      <span>{location}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="trial-aside-muted">Location data pending.</div>
              )}
              {locationsRemaining > 0 ? (
                <div className="trial-aside-muted">+{locationsRemaining} more locations</div>
              ) : null}
            </Card>
          </aside>
        </div>
      )}
    </Shell>
  );
}
