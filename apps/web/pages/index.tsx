import Link from "next/link";
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

export default function Home() {
  const [condition, setCondition] = useState("");
  const [status, setStatus] = useState("");
  const [phase, setPhase] = useState("");
  const [trials, setTrials] = useState<TrialSummary[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalPages = useMemo(() => {
    return total > 0 ? Math.ceil(total / 20) : 1;
  }, [total]);

  const fetchTrials = async (nextPage: number) => {
    setLoading(true);
    setError(null);

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

  useEffect(() => {
    void fetchTrials(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main>
      <header className="page-header">
        <span className="kicker">Clinical Trial Matching Assistant</span>
        <h1 className="title">Find the right clinical trials, faster.</h1>
        <p className="subtitle">
          Search ClinicalTrials.gov data, review eligibility text, and share
          results with your care team. This tool surfaces information only and
          does not provide medical advice.
        </p>
        <div className="meta-row">
          <Link href="/match" className="button secondary">
            Start patient matching
          </Link>
        </div>
      </header>

      <div className="layout-grid">
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
            {trials.map((trial) => (
              <article className="card trial-card" key={trial.nct_id}>
                <div className="pills">
                  {trial.status && <span className="pill">{trial.status}</span>}
                  {trial.phase && (
                    <span className="pill warm">{trial.phase}</span>
                  )}
                </div>
                <Link href={`/trials/${trial.nct_id}`} className="trial-title">
                  {trial.title}
                </Link>
                <div className="location-list">
                  {trial.locations.length > 0
                    ? trial.locations.slice(0, 3).join(" · ")
                    : "Location data pending"}
                </div>
                <div className="meta-row">
                  <span>{trial.conditions.slice(0, 3).join(" · ")}</span>
                  {trial.fetched_at && <span>Updated {trial.fetched_at}</span>}
                </div>
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
