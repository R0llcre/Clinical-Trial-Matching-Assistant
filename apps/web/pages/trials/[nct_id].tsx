import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

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

export default function TrialDetailPage() {
  const router = useRouter();
  const { nct_id } = router.query;

  const [trial, setTrial] = useState<TrialDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eligibilityExpanded, setEligibilityExpanded] = useState(false);

  useEffect(() => {
    if (!router.isReady || typeof nct_id !== "string") {
      return;
    }

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE}/api/trials/${nct_id}`);
        const payload = (await response.json()) as TrialResponse;
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error?.message || "Failed to load trial");
        }
        setTrial(payload.data ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        setTrial(null);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [router.isReady, nct_id]);

  const eligibilityText = trial?.eligibility_text ?? "";
  const eligibilityLines = eligibilityText ? eligibilityText.split("\n") : [];
  const eligibilityPreview = eligibilityLines.slice(0, 18).join("\n");
  const eligibilityTruncated = eligibilityLines.length > 18;
  const eligibilityShown =
    eligibilityTruncated && !eligibilityExpanded
      ? `${eligibilityPreview}\n\n…`
      : eligibilityText || "No eligibility text provided.";

  return (
    <main>
      <header className="page-header">
        <span className="kicker">{trial?.nct_id ?? "Trial"}</span>
        {loading ? (
          <>
            <div className="skeleton skeleton-line long" />
            <div className="skeleton skeleton-line medium" />
          </>
        ) : (
          <>
            {trial && <h1 className="title">{trial.title}</h1>}
            {trial && (
              <div className="pills">
                {trial.status && <span className="pill">{trial.status}</span>}
                {trial.phase && <span className="pill warm">{trial.phase}</span>}
                {trial.fetched_at && (
                  <span className="pill">updated {trial.fetched_at}</span>
                )}
              </div>
            )}
          </>
        )}
        {error && <p className="notice">{error}</p>}
      </header>

      {loading && (
        <div className="detail-grid">
          <section className="detail-block">
            <div className="skeleton skeleton-block" />
          </section>
          <section className="detail-block">
            <div className="skeleton skeleton-block" />
          </section>
          <section className="detail-block">
            <div className="skeleton skeleton-block" />
          </section>
          <section className="detail-block">
            <div className="skeleton skeleton-block" />
          </section>
        </div>
      )}

      {trial && (
        <div className="detail-grid">
          <section className="detail-block">
            <h3>Summary</h3>
            <pre>
              {trial.summary ||
                "Summary unavailable. Review eligibility criteria for details."}
            </pre>
          </section>
          <section className="detail-block">
            <h3>Eligibility</h3>
            <pre>{eligibilityShown}</pre>
            {eligibilityTruncated && (
              <button
                type="button"
                className="link-button"
                onClick={() => setEligibilityExpanded((value) => !value)}
              >
                {eligibilityExpanded ? "Collapse" : "Expand"}
              </button>
            )}
          </section>
          <section className="detail-block">
            <h3>Parsed Criteria</h3>
            <div className="pills">
              {trial.criteria_parser_version && (
                <span className="pill warm">{trial.criteria_parser_version}</span>
              )}
              {trial.coverage_stats?.total_rules !== undefined && (
                <span className="pill">
                  rules {trial.coverage_stats.total_rules}
                </span>
              )}
              {trial.coverage_stats?.unknown_rules !== undefined && (
                <span className="pill">
                  unknown {trial.coverage_stats.unknown_rules}
                </span>
              )}
            </div>
            {trial.criteria && trial.criteria.length > 0 ? (
              <ul className="checklist-list">
                {trial.criteria.map((rule) => (
                  <li key={rule.id}>
                    <span className="pill">{rule.type}</span>
                    <strong>
                      {rule.field} {rule.operator} {String(rule.value ?? "")}
                      {rule.unit ? ` ${rule.unit}` : ""}
                    </strong>
                    <span>{rule.evidence_text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="notice">No parsed criteria available yet.</p>
            )}
          </section>
          <section className="detail-block">
            <h3>Locations</h3>
            <ul className="location-list">
              {trial.locations.length > 0
                ? trial.locations.map((location) => (
                    <li key={location}>{location}</li>
                  ))
                : "Location data pending"}
            </ul>
          </section>
          <section className="detail-block">
            <h3>Conditions</h3>
            <div className="pills">
              {trial.conditions.length > 0
                ? trial.conditions.map((condition) => (
                    <span className="pill" key={condition}>
                      {condition}
                    </span>
                  ))
                : "Condition data pending"}
            </div>
          </section>
          <div className="meta-row">
            <Link href="/" className="button secondary">
              Back to browse
            </Link>
          </div>
        </div>
      )}
    </main>
  );
}
