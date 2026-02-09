import Link from "next/link";
import type { GetServerSideProps } from "next";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

type TrialSummary = {
  nct_id: string;
  title: string;
  status?: string | null;
  phase?: string | null;
  conditions: string[];
  locations: string[];
  fetched_at?: string | null;
};

type TrialsResponse = {
  ok: boolean;
  data?: {
    trials: TrialSummary[];
    total: number;
    page: number;
    page_size: number;
  };
  error?: {
    code: string;
    message: string;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const formatFetchedDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  // API timestamps may include fractional seconds without timezone. Keep it stable and readable.
  return value.length >= 10 ? value.slice(0, 10) : value;
};

type HomeProps = {
  initialTrials: TrialSummary[];
  initialTotal: number;
  initialPage: number;
  initialPageSize: number;
  initialCondition: string;
  initialStatus: string;
  initialPhase: string;
};

export const getServerSideProps: GetServerSideProps<HomeProps> = async (ctx) => {
  const condition =
    typeof ctx.query.condition === "string" ? ctx.query.condition : "";
  const status = typeof ctx.query.status === "string" ? ctx.query.status : "";
  const phase = typeof ctx.query.phase === "string" ? ctx.query.phase : "";
  const page =
    typeof ctx.query.page === "string" ? Number(ctx.query.page) : 1;
  const pageSize =
    typeof ctx.query.page_size === "string" ? Number(ctx.query.page_size) : 20;

  const safePage = Number.isFinite(page) && page > 0 ? page : 1;
  const safePageSize =
    Number.isFinite(pageSize) && pageSize > 0 && pageSize <= 50
      ? pageSize
      : 20;

  const params = new URLSearchParams();
  if (condition.trim()) {
    params.set("condition", condition.trim());
  }
  if (status) {
    params.set("status", status);
  }
  if (phase) {
    params.set("phase", phase);
  }
  params.set("page", String(safePage));
  params.set("page_size", String(safePageSize));

  try {
    const response = await fetch(`${API_BASE}/api/trials?${params.toString()}`);
    const payload = (await response.json()) as TrialsResponse;
    if (!response.ok || !payload.ok || !payload.data) {
      return {
        props: {
          initialTrials: [],
          initialTotal: 0,
          initialPage: safePage,
          initialPageSize: safePageSize,
          initialCondition: condition,
          initialStatus: status,
          initialPhase: phase,
        },
      };
    }
    return {
      props: {
        initialTrials: payload.data.trials ?? [],
        initialTotal: payload.data.total ?? 0,
        initialPage: payload.data.page ?? safePage,
        initialPageSize: payload.data.page_size ?? safePageSize,
        initialCondition: condition,
        initialStatus: status,
        initialPhase: phase,
      },
    };
  } catch {
    return {
      props: {
        initialTrials: [],
        initialTotal: 0,
        initialPage: safePage,
        initialPageSize: safePageSize,
        initialCondition: condition,
        initialStatus: status,
        initialPhase: phase,
      },
    };
  }
};

export default function Home(props: HomeProps) {
  const [condition, setCondition] = useState(props.initialCondition);
  const [status, setStatus] = useState(props.initialStatus);
  const [phase, setPhase] = useState(props.initialPhase);
  const [trials, setTrials] = useState<TrialSummary[]>(props.initialTrials);
  const [page, setPage] = useState(props.initialPage);
  const [total, setTotal] = useState(props.initialTotal);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastSyncedDate = useMemo(() => {
    let latest: string | null = null;
    for (const trial of trials) {
      const value = trial.fetched_at;
      if (!value) {
        continue;
      }
      if (!latest || value > latest) {
        latest = value;
      }
    }
    return formatFetchedDate(latest);
  }, [trials]);

  const totalPages = useMemo(() => {
    return total > 0 ? Math.ceil(total / 20) : 1;
  }, [total]);

  const fetchTrials = async (
    nextPage: number,
    overrides?: Partial<{ condition: string; status: string; phase: string }>
  ) => {
    setLoading(true);
    setError(null);

    const conditionValue = overrides?.condition ?? condition;
    const statusValue = overrides?.status ?? status;
    const phaseValue = overrides?.phase ?? phase;

    const params = new URLSearchParams();
    if (conditionValue.trim()) {
      params.set("condition", conditionValue.trim());
    }
    if (statusValue) {
      params.set("status", statusValue);
    }
    if (phaseValue) {
      params.set("phase", phaseValue);
    }
    params.set("page", String(nextPage));
    params.set("page_size", "20");

    try {
      const response = await fetch(
        `${API_BASE}/api/trials?${params.toString()}`
      );
      const payload = (await response.json()) as TrialsResponse;
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error?.message || "Search failed");
      }
      setTrials(payload.data?.trials ?? []);
      setTotal(payload.data?.total ?? 0);
      setPage(payload.data?.page ?? nextPage);
    } catch (err) {
      setTrials([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    fetchTrials(1);
  };

  const suggestedConditions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const trial of trials) {
      for (const rawCondition of trial.conditions ?? []) {
        const value = rawCondition.trim();
        if (!value) {
          continue;
        }
        counts.set(value, (counts.get(value) ?? 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 10)
      .map(([value]) => value);
  }, [trials]);

  useEffect(() => {
    // Keep client state aligned if user navigates with back/forward and SSR query changes.
    setCondition(props.initialCondition);
    setStatus(props.initialStatus);
    setPhase(props.initialPhase);
    setTrials(props.initialTrials);
    setTotal(props.initialTotal);
    setPage(props.initialPage);
  }, [
    props.initialCondition,
    props.initialStatus,
    props.initialPhase,
    props.initialPage,
    props.initialTotal,
    props.initialTrials,
  ]);

  return (
    <main>
      <header className="hero">
        <div className="hero-grid">
          <div className="hero-copy">
            <span className="kicker">Clinical Trial Matching Assistant</span>
            <h1 className="title">Find the right clinical trials, faster.</h1>
            <p className="subtitle">
              Search synced ClinicalTrials.gov data, review eligibility text,
              and run explainable matching. This tool surfaces information only
              and does not provide medical advice.
            </p>
            <div className="hero-actions">
              <Link href="/match" className="button">
                Start patient matching
              </Link>
              <a className="button secondary" href="#browse">
                Browse trials
              </a>
            </div>
          </div>
          <div className="card hero-stats">
            <h2 className="section-title">Preview dataset</h2>
            <div className="stats-grid">
              <div className="stat">
                <div className="stat-value">{total || "—"}</div>
                <div className="stat-label">trials available</div>
              </div>
              <div className="stat">
                <div className="stat-value">{lastSyncedDate || "—"}</div>
                <div className="stat-label">last sync date</div>
              </div>
            </div>
            <p className="help-text">
              Tip: start broad (for example “breast cancer”) then narrow by
              status and phase.
            </p>
          </div>
        </div>
      </header>

      <div className="layout-grid" id="browse">
        <aside className="stack">
          <section className="card">
            <h2 className="section-title">Search</h2>
            <form className="search-panel" onSubmit={handleSubmit}>
              <div className="field">
                <label htmlFor="condition">Condition</label>
                <input
                  id="condition"
                  name="condition"
                  placeholder="e.g. diabetes, breast cancer"
                  value={condition}
                  onChange={(event) => setCondition(event.target.value)}
                />
                {suggestedConditions.length > 0 && (
                  <div className="suggestions">
                    <span className="suggestions-label">Try:</span>
                    <div className="pills">
                      {suggestedConditions.map((value) => (
                        <button
                          key={value}
                          type="button"
                          className="pill pill-button"
                          onClick={() => {
                            setCondition(value);
                            void fetchTrials(1, { condition: value });
                          }}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="field">
                <label htmlFor="status">Status</label>
                <select
                  id="status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="">Any</option>
                  <option value="RECRUITING">Recruiting</option>
                  <option value="NOT_YET_RECRUITING">Not yet recruiting</option>
                  <option value="ACTIVE_NOT_RECRUITING">
                    Active, not recruiting
                  </option>
                  <option value="COMPLETED">Completed</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="phase">Phase</label>
                <select
                  id="phase"
                  value={phase}
                  onChange={(event) => setPhase(event.target.value)}
                >
                  <option value="">Any</option>
                  <option value="EARLY_PHASE1">Early Phase 1</option>
                  <option value="PHASE1">Phase 1</option>
                  <option value="PHASE2">Phase 2</option>
                  <option value="PHASE3">Phase 3</option>
                  <option value="PHASE4">Phase 4</option>
                </select>
              </div>
              <button className="button" type="submit" disabled={loading}>
                {loading ? "Searching..." : "Search trials"}
              </button>
            </form>
          </section>

          <section className="card subtle">
            <h2 className="section-title">How to use</h2>
            <p className="help-text">
              Start with a broad condition (for example “breast cancer”) and
              then narrow by status and phase. Use the trial detail page to
              review eligibility text before sharing with a clinician.
            </p>
          </section>
        </aside>

        <section className="stack">
          <div className="meta-row">
            <span>
              {total > 0
                ? `${total} trials found`
                : "Showing the latest synced trials."}
            </span>
            {error && <span className="notice">{error}</span>}
          </div>

          <section className="trials-grid">
            {loading && trials.length === 0 && (
              <>
                {Array.from({ length: 4 }).map((_, index) => (
                  <article className="card trial-card" key={`skeleton-${index}`}>
                    <div className="skeleton skeleton-line short" />
                    <div className="skeleton skeleton-line long" />
                    <div className="skeleton skeleton-line medium" />
                    <div className="skeleton skeleton-line long" />
                  </article>
                ))}
              </>
            )}

            {trials.map((trial) => (
              <article className="card trial-card" key={trial.nct_id}>
                <div className="pills">
                  <span className="pill warm">{trial.nct_id}</span>
                  {trial.status && <span className="pill">{trial.status}</span>}
                  {trial.phase && <span className="pill">{trial.phase}</span>}
                </div>
                <Link href={`/trials/${trial.nct_id}`} className="trial-title">
                  {trial.title}
                </Link>
                <div className="trial-subtitle">
                  {trial.locations.length > 0
                    ? trial.locations.slice(0, 3).join(" · ")
                    : "Location data pending"}
                </div>
                <div className="pills">
                  {trial.conditions.slice(0, 4).map((value) => (
                    <span className="pill" key={`${trial.nct_id}-${value}`}>
                      {value}
                    </span>
                  ))}
                </div>
                {trial.fetched_at && (
                  <div className="meta-row">
                    <span>Synced {formatFetchedDate(trial.fetched_at)}</span>
                  </div>
                )}
              </article>
            ))}
          </section>

          {trials.length > 0 && (
            <div className="pagination">
              <button
                className="button secondary"
                onClick={() => fetchTrials(Math.max(1, page - 1))}
                disabled={loading || page <= 1}
              >
                Previous
              </button>
              <span>
                Page {page} of {totalPages}
              </span>
              <button
                className="button secondary"
                onClick={() => fetchTrials(Math.min(totalPages, page + 1))}
                disabled={loading || page >= totalPages}
              >
                Next
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
