import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  History,
  PencilLine,
  Play,
  UserRound,
} from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Field } from "../../components/ui/Field";
import { Input } from "../../components/ui/Input";
import { Pill } from "../../components/ui/Pill";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import { Toast } from "../../components/ui/Toast";
import { ApiError } from "../../lib/http/client";
import { ensureSession, withSessionRetry } from "../../lib/session/session";

import { createMatch, getPatient, listMatches } from "./api";
import type { MatchListItem, Patient } from "./types";
import styles from "./PatientDetailPage.module.css";

const formatDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value.length >= 10 ? value.slice(0, 10) : value;
};

const normalizeText = (value: unknown): string => {
  return typeof value === "string" ? value.trim() : "";
};

const shortId = (value: string) => (value.length > 8 ? value.slice(0, 8) : value);

const filtersFromMatch = (match: MatchListItem): Record<string, string> => {
  const query = match.query_json;
  if (!query || typeof query !== "object") {
    return {};
  }
  const filters = (query as { filters?: unknown }).filters;
  if (!filters || typeof filters !== "object") {
    return {};
  }
  const result: Record<string, string> = {};
  for (const [key, val] of Object.entries(filters as Record<string, unknown>)) {
    if (typeof val === "string" && val.trim()) {
      result[key] = val.trim();
    }
  }
  return result;
};

export default function PatientDetailPage() {
  const router = useRouter();
  const patientId = typeof router.query.id === "string" ? router.query.id : "";

  const [sessionStatus, setSessionStatus] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");

  const [patient, setPatient] = useState<Patient | null>(null);
  const [patientLoading, setPatientLoading] = useState(true);
  const [patientError, setPatientError] = useState<string | null>(null);

  const [history, setHistory] = useState<MatchListItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(10);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const conditionTouchedRef = useRef(false);
  const [condition, setCondition] = useState("");
  const [status, setStatus] = useState("");
  const [phase, setPhase] = useState("");
  const [country, setCountry] = useState("");
  const [state, setState] = useState("");
  const [city, setCity] = useState("");
  const [topK, setTopK] = useState("10");

  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const historyTotalPages = useMemo(() => {
    if (historyTotal <= 0) {
      return 1;
    }
    return Math.max(1, Math.ceil(historyTotal / historyPageSize));
  }, [historyPageSize, historyTotal]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const session = await ensureSession({
        envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
        allowPreviewIssue: true,
      });
      if (!cancelled) {
        setSessionStatus(session.status);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!router.isReady || !patientId) {
      return;
    }

    let cancelled = false;
    const loadPatient = async () => {
      setPatientLoading(true);
      setPatientError(null);
      try {
        const loaded = await withSessionRetry(
          (token) => getPatient({ token, patientId }),
          {
            envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
            allowPreviewIssue: true,
          }
        );
        if (cancelled) {
          return;
        }
        setPatient(loaded);

        const primary = Array.isArray(loaded.profile_json?.conditions)
          ? normalizeText(loaded.profile_json.conditions[0])
          : "";
        if (!conditionTouchedRef.current && primary) {
          setCondition(primary);
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError) {
          setPatientError(err.message);
        } else if (err instanceof Error) {
          setPatientError(err.message);
        } else {
          setPatientError("Failed to load patient");
        }
        setPatient(null);
      } finally {
        if (!cancelled) {
          setPatientLoading(false);
        }
      }
    };

    void loadPatient();
    return () => {
      cancelled = true;
    };
  }, [patientId, router.isReady]);

  useEffect(() => {
    if (!patientId) {
      return;
    }

    let cancelled = false;
    const loadHistory = async () => {
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const data = await withSessionRetry(
          (token) =>
            listMatches({
              token,
              patientProfileId: patientId,
              page: historyPage,
              pageSize: historyPageSize,
            }),
          {
            envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
            allowPreviewIssue: true,
          }
        );
        if (cancelled) {
          return;
        }
        setHistory(Array.isArray(data.matches) ? data.matches : []);
        setHistoryTotal(Number.isFinite(data.total) ? data.total : 0);
      } catch (err) {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError) {
          setHistoryError(err.message);
        } else if (err instanceof Error) {
          setHistoryError(err.message);
        } else {
          setHistoryError("Failed to load match history");
        }
        setHistory([]);
        setHistoryTotal(0);
      } finally {
        if (!cancelled) {
          setHistoryLoading(false);
        }
      }
    };

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, [historyPage, historyPageSize, patientId]);

  useEffect(() => {
    if (historyPage > historyTotalPages) {
      setHistoryPage(historyTotalPages);
    }
  }, [historyPage, historyTotalPages]);

  const runMatch = async () => {
    if (!patientId || runLoading) {
      return;
    }
    setRunError(null);

    const nextErrors: string[] = [];
    const parsedTopK = Number(topK);
    if (!normalizeText(condition)) {
      nextErrors.push("Condition is required.");
    }
    if (!Number.isFinite(parsedTopK) || parsedTopK < 1 || parsedTopK > 50) {
      nextErrors.push("Top K must be between 1 and 50.");
    }
    if (nextErrors.length > 0) {
      setRunError(nextErrors.join(" "));
      return;
    }

    const trimmedFilters: Record<string, string> = {};
    const maybeSet = (key: string, value: string) => {
      const trimmed = value.trim();
      if (trimmed) {
        trimmedFilters[key] = trimmed;
      }
    };
    maybeSet("condition", condition);
    maybeSet("status", status);
    maybeSet("phase", phase);
    maybeSet("country", country);
    maybeSet("state", state);
    maybeSet("city", city);

    setRunLoading(true);
    try {
      const result = await withSessionRetry(
        (token) =>
          createMatch({
            token,
            patientProfileId: patientId,
            topK: parsedTopK,
            filters: trimmedFilters,
          }),
        {
          envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
          allowPreviewIssue: true,
        }
      );
      await router.push(`/matches/${result.match_id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setRunError(err.message);
      } else if (err instanceof Error) {
        setRunError(err.message);
      } else {
        setRunError("Unable to run matching");
      }
    } finally {
      setRunLoading(false);
    }
  };

  const patientKicker = patient ? `Patient ${shortId(patient.id)}` : "Patient";
  const patientTitle = patient ? patient.profile_json?.conditions?.[0] || "Patient profile" : "Patient profile";

  const demo = patient?.profile_json?.demographics;
  const ageValue = typeof demo?.age === "number" ? Math.trunc(demo.age) : null;
  const sexValue = normalizeText(demo?.sex);
  const conditionsList = Array.isArray(patient?.profile_json?.conditions)
    ? patient?.profile_json?.conditions.filter((entry) => normalizeText(entry))
    : [];

  return (
    <Shell
      className={styles.page}
      kicker={patientKicker}
      title={patientTitle}
      subtitle="Review a patient profile, run matching with different filters, and revisit past match results."
      actions={
        <>
          <Link href="/patients" className="ui-button ui-button--ghost ui-button--md">
            <span className="ui-button__icon" aria-hidden="true">
              <ChevronLeft size={18} />
            </span>
            <span className="ui-button__label">Patients</span>
          </Link>
          {patientId ? (
            <Link
              href={`/patients/${encodeURIComponent(patientId)}/edit`}
              className="ui-button ui-button--secondary ui-button--md"
            >
              <span className="ui-button__icon" aria-hidden="true">
                <PencilLine size={18} />
              </span>
              <span className="ui-button__label">Edit patient</span>
            </Link>
          ) : null}
        </>
      }
    >
      {sessionStatus === "unavailable" ? (
        <Toast
          tone="warning"
          title="Session unavailable"
          description="This preview could not start an authenticated session. Try refreshing the page."
        />
      ) : null}

      {patientError ? (
        <Toast tone="danger" title="Could not load patient" description={patientError} />
      ) : null}
      {historyError ? (
        <Toast tone="danger" title="Could not load match history" description={historyError} />
      ) : null}
      {runError ? (
        <Toast tone="danger" title="Unable to run match" description={runError} />
      ) : null}

      <div className={styles.layout}>
        <div className={styles.main}>
          <Card className={styles.card}>
            <div className={styles.cardHeader}>
              <div>
                <h2>Run match</h2>
                <p>Adjust filters and run matching against the current dataset.</p>
              </div>
            </div>

            <div className={styles.formGrid}>
              <Field label="Condition" htmlFor="match-condition" hint="Defaults to the first patient condition.">
                <Input
                  id="match-condition"
                  value={condition}
                  onChange={(event) => {
                    conditionTouchedRef.current = true;
                    setCondition(event.target.value);
                  }}
                  placeholder="Breast Cancer"
                />
              </Field>

              <Field label="Top K" htmlFor="match-topk" hint="How many trials to return (1-50).">
                <Input
                  id="match-topk"
                  inputMode="numeric"
                  value={topK}
                  onChange={(event) => setTopK(event.target.value)}
                  placeholder="10"
                />
              </Field>

              <Field label="Status" htmlFor="match-status" hint="Optional.">
                <Select
                  id="match-status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="">Any</option>
                  <option value="RECRUITING">Recruiting</option>
                  <option value="NOT_YET_RECRUITING">Not yet recruiting</option>
                  <option value="ACTIVE_NOT_RECRUITING">Active, not recruiting</option>
                  <option value="COMPLETED">Completed</option>
                </Select>
              </Field>

              <Field label="Phase" htmlFor="match-phase" hint="Optional.">
                <Select
                  id="match-phase"
                  value={phase}
                  onChange={(event) => setPhase(event.target.value)}
                >
                  <option value="">Any</option>
                  <option value="EARLY_PHASE1">Early Phase 1</option>
                  <option value="PHASE1">Phase 1</option>
                  <option value="PHASE2">Phase 2</option>
                  <option value="PHASE3">Phase 3</option>
                  <option value="PHASE4">Phase 4</option>
                </Select>
              </Field>

              <Field label="Country" htmlFor="match-country" hint="Optional (free text).">
                <Input
                  id="match-country"
                  value={country}
                  onChange={(event) => setCountry(event.target.value)}
                  placeholder="United States"
                />
              </Field>

              <Field label="State" htmlFor="match-state" hint="Optional (free text).">
                <Input
                  id="match-state"
                  value={state}
                  onChange={(event) => setState(event.target.value)}
                  placeholder="NY"
                />
              </Field>

              <Field label="City" htmlFor="match-city" hint="Optional (free text).">
                <Input
                  id="match-city"
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                  placeholder="New York"
                />
              </Field>
            </div>

            <div className={styles.actions}>
              <Button
                tone="primary"
                size="md"
                iconLeft={<Play size={18} aria-hidden="true" />}
                onClick={runMatch}
                disabled={runLoading || patientLoading || sessionStatus === "unavailable"}
              >
                {runLoading ? "Running..." : "Run match"}
              </Button>
              <Link href="/match" className="ui-button ui-button--ghost ui-button--md">
                One-off match
              </Link>
            </div>
          </Card>

          <Card className={styles.card}>
            <div className={styles.cardHeader}>
              <div>
                <h2>Match history</h2>
                <p>Matches are scoped to your preview session and this patient profile.</p>
              </div>
              <div>
                <Select
                  aria-label="History page size"
                  value={String(historyPageSize)}
                  onChange={(event) => {
                    const next = Number(event.target.value);
                    setHistoryPageSize(Number.isFinite(next) ? next : 10);
                    setHistoryPage(1);
                  }}
                >
                  <option value="5">5 / page</option>
                  <option value="10">10 / page</option>
                  <option value="20">20 / page</option>
                </Select>
              </div>
            </div>

            {historyLoading ? (
              <div>
                {Array.from({ length: 5 }).map((_, idx) => (
                  <div key={idx} style={{ padding: "12px 0" }}>
                    <Skeleton width="long" />
                    <div style={{ marginTop: 10 }}>
                      <Skeleton width="medium" />
                    </div>
                  </div>
                ))}
              </div>
            ) : history.length === 0 ? (
              <EmptyState
                icon={<History size={28} aria-hidden="true" />}
                title="No matches yet"
                description="Run a match to generate results for this patient."
              />
            ) : (
              <div className={styles.historyList}>
                {history.map((match) => {
                  const filters = filtersFromMatch(match);
                  const created = formatDate(match.created_at);
                  return (
                    <div key={match.id} className={styles.historyRow}>
                      <div>
                        <div style={{ fontWeight: 700, color: "var(--ink)" }}>
                          Match {shortId(match.id)}
                        </div>
                        <div className={styles.historyMeta}>
                          {created ? (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                              <CalendarClock size={14} aria-hidden="true" />
                              <span>{created}</span>
                            </span>
                          ) : null}
                          <span className={styles.filters}>
                            {Object.entries(filters)
                              .slice(0, 5)
                              .map(([key, value]) => (
                                <Pill key={`${match.id}-${key}`} tone="neutral">
                                  {key}: {value}
                                </Pill>
                              ))}
                          </span>
                        </div>
                      </div>
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
                        <Link
                          href={`/matches/${match.id}`}
                          className="ui-button ui-button--secondary ui-button--sm"
                        >
                          View results
                        </Link>
                      </div>
                    </div>
                  );
                })}

                <div className={styles.actions} style={{ justifyContent: "space-between" }}>
                  <div style={{ color: "var(--muted)", fontSize: 13 }}>
                    Page {historyPage} / {historyTotalPages}
                  </div>
                  <div style={{ display: "inline-flex", gap: 8 }}>
                    <Button
                      tone="secondary"
                      size="sm"
                      onClick={() => setHistoryPage((value) => Math.max(1, value - 1))}
                      disabled={historyPage <= 1}
                      iconLeft={<ChevronLeft size={16} aria-hidden="true" />}
                    >
                      Prev
                    </Button>
                    <Button
                      tone="secondary"
                      size="sm"
                      onClick={() =>
                        setHistoryPage((value) => Math.min(historyTotalPages, value + 1))
                      }
                      disabled={historyPage >= historyTotalPages}
                      iconRight={<ChevronRight size={16} aria-hidden="true" />}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>

        <div className={styles.aside}>
          <Card className={styles.asideCard}>
            <h3 className={styles.asideTitle}>Patient summary</h3>
            {patientLoading ? (
              <div style={{ marginTop: 12 }}>
                <Skeleton width="long" />
                <div style={{ marginTop: 10 }}>
                  <Skeleton width="medium" />
                </div>
              </div>
            ) : !patient ? (
              <EmptyState
                icon={<UserRound size={28} aria-hidden="true" />}
                title="Patient unavailable"
                description="This profile may not exist in your session."
              />
            ) : (
              <>
                <div className={styles.pills}>
                  {ageValue !== null ? (
                    <Pill tone="neutral">Age {ageValue}</Pill>
                  ) : (
                    <Pill tone="warning">Age missing</Pill>
                  )}
                  {sexValue ? <Pill tone="neutral">{sexValue}</Pill> : <Pill tone="warning">Sex missing</Pill>}
                  <Pill tone="brand">{conditionsList.length || 0} conditions</Pill>
                </div>

                <div className={styles.facts}>
                  <div className={styles.factRow}>
                    <div className={styles.factKey}>Patient ID</div>
                    <div className={styles.factValue}>{shortId(patient.id)}</div>
                  </div>
                  <div className={styles.factRow}>
                    <div className={styles.factKey}>Source</div>
                    <div className={styles.factValue}>{normalizeText(patient.source) || "manual"}</div>
                  </div>
                  <div className={styles.factRow}>
                    <div className={styles.factKey}>Created</div>
                    <div className={styles.factValue}>{formatDate(patient.created_at) ?? "—"}</div>
                  </div>
                </div>

                {conditionsList.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ color: "var(--muted)", fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                      Conditions
                    </div>
                    <div className={styles.pills} style={{ marginTop: 8 }}>
                      {conditionsList.slice(0, 8).map((entry) => (
                        <Pill key={entry} tone="neutral">
                          {entry}
                        </Pill>
                      ))}
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </Card>
        </div>
      </div>
    </Shell>
  );
}
