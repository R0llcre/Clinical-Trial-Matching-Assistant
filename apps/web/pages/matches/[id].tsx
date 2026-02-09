import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

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

const verdictClass = (verdict: string) => {
  if (verdict === "PASS") {
    return "pill verdict-pass";
  }
  if (verdict === "FAIL") {
    return "pill verdict-fail";
  }
  return "pill verdict-unknown";
};

export default function MatchResultsPage() {
  const router = useRouter();
  const { id } = router.query;

  const [jwtToken, setJwtToken] = useState(
    process.env.NEXT_PUBLIC_DEV_JWT ?? ""
  );
  const [data, setData] = useState<MatchData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const countVerdicts = (rules: RuleVerdict[]) => {
    const counts = { PASS: 0, FAIL: 0, UNKNOWN: 0 };
    for (const rule of rules) {
      counts[rule.verdict] += 1;
    }
    return counts;
  };

  useEffect(() => {
    const savedToken = window.localStorage.getItem("ctmatch.jwt");
    if (savedToken && !jwtToken) {
      setJwtToken(savedToken);
      return;
    }
    if (!jwtToken) {
      void (async () => {
        try {
          const response = await fetch(`${API_BASE}/api/auth/preview-token`);
          if (!response.ok) {
            return;
          }
          const payload = (await response.json()) as {
            ok: boolean;
            data?: { token?: string };
          };
          const token = payload.data?.token;
          if (payload.ok && token && token.trim()) {
            window.localStorage.setItem("ctmatch.jwt", token.trim());
            setJwtToken(token.trim());
          }
        } catch {
          // ignore
        }
      })();
    }
  }, [jwtToken]);

  useEffect(() => {
    if (!router.isReady || typeof id !== "string") {
      return;
    }

    const loadMatch = async () => {
      setLoading(true);
      setError(null);
      try {
        const token = (
          window.localStorage.getItem("ctmatch.jwt") ?? jwtToken
        ).trim();
        if (!token) {
          throw new Error(
            "JWT token is required. In preview deployments it can be auto-issued; otherwise open /match first."
          );
        }
        const response = await fetch(`${API_BASE}/api/matches/${id}`, {
          headers: {Authorization: `Bearer ${token}`},
        });
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

    loadMatch();
  }, [router.isReady, id, jwtToken]);

  return (
    <main>
      <div className="meta-row">
        <Link href="/match" className="button secondary">
          Back to patient form
        </Link>
        <Link href="/" className="button secondary">
          Browse trials
        </Link>
      </div>

      {loading && <p className="notice">Loading match results...</p>}
      {error && <p className="notice">{error}</p>}

      {data && (
        <>
          <header className="page-header">
            <span className="kicker">Match Results</span>
            <h1 className="title">Match {data.id}</h1>
            <p className="subtitle">
              Patient profile: {data.patient_profile_id} · Results:{" "}
              {data.results.length}
            </p>
          </header>

          <section className="trials-grid">
            {data.results.length === 0 && (
              <p className="notice">
                No matched trials were returned. Adjust patient conditions or
                match filters and try again.
              </p>
            )}
            {data.results.map((item) => (
              <article className="card trial-card result-card" key={item.nct_id}>
                <header className="result-head">
                  <div className="result-title">
                    <Link href={`/trials/${item.nct_id}`} className="trial-title">
                      {item.title || item.nct_id}
                    </Link>
                    <div className="pills">
                      <span className="pill warm">{item.nct_id}</span>
                      {item.status && (
                        <span
                          className={`pill ${statusPillClass(item.status)}`}
                          title={item.status}
                        >
                          {statusLabel(item.status)}
                        </span>
                      )}
                      {item.phase && <span className="pill">{item.phase}</span>}
                    </div>
                  </div>

                  <div className="result-metrics">
                    <div className="metric">
                      <span className="metric-label">Score</span>
                      <span className="metric-value">{item.score.toFixed(2)}</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Certainty</span>
                      <span className="metric-value">{item.certainty.toFixed(2)}</span>
                    </div>
                  </div>
                </header>

                {(() => {
                  const inclusionCounts = countVerdicts(item.checklist.inclusion);
                  const exclusionCounts = countVerdicts(item.checklist.exclusion);
                  const isExpanded = Boolean(expanded[item.nct_id]);
                  return (
                    <>
                      <div className="pills">
                        <span className="pill verdict-pass">
                          pass {inclusionCounts.PASS + exclusionCounts.PASS}
                        </span>
                        <span className="pill verdict-unknown">
                          unknown{" "}
                          {inclusionCounts.UNKNOWN + exclusionCounts.UNKNOWN}
                        </span>
                        <span className="pill verdict-fail">
                          fail {inclusionCounts.FAIL + exclusionCounts.FAIL}
                        </span>
                        <span className="pill">
                          missing {item.checklist.missing_info.length}
                        </span>
                        <button
                          type="button"
                          className="link-button"
                          onClick={() =>
                            setExpanded((prev) => ({
                              ...prev,
                              [item.nct_id]: !isExpanded,
                            }))
                          }
                        >
                          {isExpanded ? "Hide checklist" : "Show checklist"}
                        </button>
                        <Link
                          href={`/trials/${item.nct_id}`}
                          className="link-button"
                        >
                          Open trial
                        </Link>
                      </div>

                      {isExpanded && (
                        <div className="checklist-grid">
                          <section className="detail-block">
                            <h3>Inclusion</h3>
                            <ul className="checklist-list">
                              {item.checklist.inclusion.map((rule) => (
                                <li key={`inc-${item.nct_id}-${rule.rule_id}`}>
                                  <span className={verdictClass(rule.verdict)}>
                                    {rule.verdict}
                                  </span>
                                  <strong>{rule.rule_id}</strong>
                                  <span>{rule.evidence}</span>
                                </li>
                              ))}
                            </ul>
                          </section>

                          <section className="detail-block">
                            <h3>Exclusion</h3>
                            <ul className="checklist-list">
                              {item.checklist.exclusion.map((rule) => (
                                <li key={`exc-${item.nct_id}-${rule.rule_id}`}>
                                  <span className={verdictClass(rule.verdict)}>
                                    {rule.verdict}
                                  </span>
                                  <strong>{rule.rule_id}</strong>
                                  <span>{rule.evidence}</span>
                                </li>
                              ))}
                            </ul>
                          </section>
                        </div>
                      )}
                    </>
                  );
                })()}

                <section className="detail-block">
                  <h3>Missing Info</h3>
                  <div className="pills">
                    {item.checklist.missing_info.length > 0
                      ? item.checklist.missing_info.map((field) => (
                          <span className="pill" key={`${item.nct_id}-${field}`}>
                            {field}
                          </span>
                        ))
                      : "No critical missing fields"}
                  </div>
                </section>
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
