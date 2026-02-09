import Link from "next/link";
import type { GetServerSideProps } from "next";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

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

const statusPillClass = (value?: string | null) => {
  if (!value) {
    return "";
  }
  if (value === "RECRUITING") {
    return "status-recruiting";
  }
  if (value === "NOT_YET_RECRUITING") {
    return "status-not-yet";
  }
  if (value === "ACTIVE_NOT_RECRUITING") {
    return "status-active";
  }
  if (value === "COMPLETED") {
    return "status-completed";
  }
  return "";
};

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
  const router = useRouter();
  const [condition, setCondition] = useState(props.initialCondition);
  const [status, setStatus] = useState(props.initialStatus);
  const [phase, setPhase] = useState(props.initialPhase);
  const [trials, setTrials] = useState<TrialSummary[]>(props.initialTrials);
  const [page, setPage] = useState(props.initialPage);
  const [pageSize, setPageSize] = useState(props.initialPageSize);
  const [total, setTotal] = useState(props.initialTotal);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
    return total > 0 ? Math.ceil(total / pageSize) : 1;
  }, [total, pageSize]);

  const buildQuery = (input: {
    conditionValue: string;
    statusValue: string;
    phaseValue: string;
    pageValue: number;
    pageSizeValue: number;
  }) => {
    const query: Record<string, string> = {};
    const trimmedCondition = input.conditionValue.trim();
    if (trimmedCondition) {
      query.condition = trimmedCondition;
    }
    if (input.statusValue) {
      query.status = input.statusValue;
    }
    if (input.phaseValue) {
      query.phase = input.phaseValue;
    }
    if (input.pageValue > 1) {
      query.page = String(input.pageValue);
    }
    if (input.pageSizeValue !== 20) {
      query.page_size = String(input.pageSizeValue);
    }
    return query;
  };

  const fetchTrials = async (input: {
    conditionValue: string;
    statusValue: string;
    phaseValue: string;
    pageValue: number;
    pageSizeValue: number;
  }) => {
    setLoading(true);
    setError(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const params = new URLSearchParams();
    if (input.conditionValue.trim()) {
      params.set("condition", input.conditionValue.trim());
    }
    if (input.statusValue) {
      params.set("status", input.statusValue);
    }
    if (input.phaseValue) {
      params.set("phase", input.phaseValue);
    }
    params.set("page", String(input.pageValue));
    params.set("page_size", String(input.pageSizeValue));

    try {
      const response = await fetch(
        `${API_BASE}/api/trials?${params.toString()}`,
        { signal: controller.signal }
      );
      const payload = (await response.json()) as TrialsResponse;
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error?.message || "Search failed");
      }
      setTrials(payload.data?.trials ?? []);
      setTotal(payload.data?.total ?? 0);
      setPage(payload.data?.page ?? input.pageValue);
      setPageSize(payload.data?.page_size ?? input.pageSizeValue);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setTrials([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = buildQuery({
      conditionValue: condition,
      statusValue: status,
      phaseValue: phase,
      pageValue: 1,
      pageSizeValue: pageSize,
    });
    void router.push({ pathname: "/", query }, undefined, { shallow: true });
  };

  const clearFilters = () => {
    setCondition("");
    setStatus("");
    setPhase("");
    const query = buildQuery({
      conditionValue: "",
      statusValue: "",
      phaseValue: "",
      pageValue: 1,
      pageSizeValue: pageSize,
    });
    void router.push({ pathname: "/", query }, undefined, { shallow: true });
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
    // When Next.js re-hydrates new SSR props (non-shallow navigation), prefer them.
    abortRef.current?.abort();
    setLoading(false);
    setError(null);
    setCondition(props.initialCondition);
    setStatus(props.initialStatus);
    setPhase(props.initialPhase);
    setTrials(props.initialTrials);
    setTotal(props.initialTotal);
    setPage(props.initialPage);
    setPageSize(props.initialPageSize);
  }, [
    props.initialCondition,
    props.initialStatus,
    props.initialPhase,
    props.initialPage,
    props.initialPageSize,
    props.initialTotal,
    props.initialTrials,
  ]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }

    const nextCondition =
      typeof router.query.condition === "string" ? router.query.condition : "";
    const nextStatus =
      typeof router.query.status === "string" ? router.query.status : "";
    const nextPhase =
      typeof router.query.phase === "string" ? router.query.phase : "";
    const nextPageRaw =
      typeof router.query.page === "string" ? Number(router.query.page) : 1;
    const nextPageSizeRaw =
      typeof router.query.page_size === "string"
        ? Number(router.query.page_size)
        : 20;

    const safePage =
      Number.isFinite(nextPageRaw) && nextPageRaw > 0 ? nextPageRaw : 1;
    const safePageSize =
      Number.isFinite(nextPageSizeRaw) &&
      nextPageSizeRaw > 0 &&
      nextPageSizeRaw <= 50
        ? nextPageSizeRaw
        : 20;

    const shouldFetch =
      nextCondition !== props.initialCondition ||
      nextStatus !== props.initialStatus ||
      nextPhase !== props.initialPhase ||
      safePage !== props.initialPage ||
      safePageSize !== props.initialPageSize;

    setCondition(nextCondition);
    setStatus(nextStatus);
    setPhase(nextPhase);
    setPage(safePage);
    setPageSize(safePageSize);

    if (!shouldFetch) {
      return;
    }

    void fetchTrials({
      conditionValue: nextCondition,
      statusValue: nextStatus,
      phaseValue: nextPhase,
      pageValue: safePage,
      pageSizeValue: safePageSize,
    });
  }, [
    router.isReady,
    router.asPath,
    props.initialCondition,
    props.initialStatus,
    props.initialPhase,
    props.initialPage,
    props.initialPageSize,
  ]);

  return (
    <main>
      <header className="hero">
        <div className="card hero-shell">
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
          <div className="card subtle hero-stats">
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
        </div>
      </header>

      <div className="layout-grid" id="browse">
        <aside className="stack sidebar">
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
                            const query = buildQuery({
                              conditionValue: value,
                              statusValue: status,
                              phaseValue: phase,
                              pageValue: 1,
                              pageSizeValue: pageSize,
                            });
                            void router.push(
                              { pathname: "/", query },
                              undefined,
                              { shallow: true }
                            );
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
            <div className="meta-select">
              <label htmlFor="page_size" className="sr-only">
                Page size
              </label>
              <select
                id="page_size"
                value={String(pageSize)}
                onChange={(event) => {
                  const nextSize = Number(event.target.value);
                  const query = buildQuery({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    pageValue: 1,
                    pageSizeValue: nextSize,
                  });
                  void router.push(
                    { pathname: "/", query },
                    undefined,
                    { shallow: true }
                  );
                }}
                disabled={loading}
              >
                <option value="20">20 / page</option>
                <option value="50">50 / page</option>
              </select>
            </div>
            {(condition || status || phase) && (
              <button
                type="button"
                className="button ghost"
                onClick={clearFilters}
                disabled={loading}
              >
                Clear filters
              </button>
            )}
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

            {!loading && trials.length === 0 && (
              <article className="card subtle empty-state">
                <h3 className="section-title">No trials found.</h3>
                <p className="help-text">
                  Try a broader condition, remove filters, or browse the latest
                  synced trials.
                </p>
                <div className="hero-actions">
                  <button
                    type="button"
                    className="button"
                    onClick={clearFilters}
                  >
                    Clear filters
                  </button>
                  <Link href="/match" className="button secondary">
                    Try matching instead
                  </Link>
                </div>
              </article>
            )}

            {trials.map((trial) => (
              <article className="card trial-card" key={trial.nct_id}>
                <div className="pills">
                  <span className="pill warm">{trial.nct_id}</span>
                  {trial.status && (
                    <span
                      className={`pill ${statusPillClass(trial.status)}`}
                      title={trial.status}
                    >
                      {statusLabel(trial.status)}
                    </span>
                  )}
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
                    <Link
                      href={`/trials/${trial.nct_id}`}
                      className="link-button"
                    >
                      View details
                    </Link>
                  </div>
                )}
              </article>
            ))}
          </section>

          {trials.length > 0 && (
            <div className="pagination">
              <button
                className="button secondary"
                onClick={() => {
                  const query = buildQuery({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    pageValue: Math.max(1, page - 1),
                    pageSizeValue: pageSize,
                  });
                  void router.push(
                    { pathname: "/", query },
                    undefined,
                    { shallow: true }
                  );
                }}
                disabled={loading || page <= 1}
              >
                Previous
              </button>
              <span>
                Page {page} of {totalPages}
              </span>
              <button
                className="button secondary"
                onClick={() => {
                  const query = buildQuery({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    pageValue: Math.min(totalPages, page + 1),
                    pageSizeValue: pageSize,
                  });
                  void router.push(
                    { pathname: "/", query },
                    undefined,
                    { shallow: true }
                  );
                }}
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
