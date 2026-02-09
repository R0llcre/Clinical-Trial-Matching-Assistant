import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

type ApiError = {
  code: string;
  message: string;
};

type CreatePatientResponse = {
  ok: boolean;
  data?: {
    id: string;
  };
  error?: ApiError;
};

type CreateMatchResponse = {
  ok: boolean;
  data?: {
    match_id: string;
  };
  error?: ApiError;
};

type TrialForSuggestions = {
  conditions: string[];
};

type TrialsSuggestionResponse = {
  ok: boolean;
  data?: {
    trials: TrialForSuggestions[];
  };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function MatchPage() {
  const router = useRouter();
  const [jwtToken, setJwtToken] = useState(
    process.env.NEXT_PUBLIC_DEV_JWT ?? ""
  );
  const [showAuthAdvanced, setShowAuthAdvanced] = useState(false);
  const [age, setAge] = useState("45");
  const [sex, setSex] = useState("female");
  const [conditions, setConditions] = useState("Leukemia");
  const [status, setStatus] = useState("");
  const [phase, setPhase] = useState("");
  const [topK, setTopK] = useState("10");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conditionSuggestions, setConditionSuggestions] = useState<string[]>([]);

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
          // ignore; preview token endpoint may be disabled.
        }
      })();
    }
  }, [jwtToken]);

  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/trials?page=1&page_size=50`);
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as TrialsSuggestionResponse;
        const trials = payload.ok ? payload.data?.trials ?? [] : [];

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

        const suggestions = Array.from(counts.entries())
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
          .slice(0, 12)
          .map(([value]) => value);
        setConditionSuggestions(suggestions);
      } catch {
        // ignore
      }
    })();
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const parsedAge = Number(age);
    const parsedTopK = Number(topK);
    if (
      Number.isNaN(parsedAge) ||
      parsedAge < 0 ||
      Number.isNaN(parsedTopK) ||
      parsedTopK < 1
    ) {
      setLoading(false);
      setError("Age and top_k must be valid positive numbers.");
      return;
    }
    if (!jwtToken.trim()) {
      try {
        const response = await fetch(`${API_BASE}/api/auth/preview-token`);
        if (response.ok) {
          const payload = (await response.json()) as {
            ok: boolean;
            data?: { token?: string };
          };
          const token = payload.data?.token;
          if (payload.ok && token && token.trim()) {
            window.localStorage.setItem("ctmatch.jwt", token.trim());
            setJwtToken(token.trim());
          }
        }
      } catch {
        // ignore
      }
      if (!window.localStorage.getItem("ctmatch.jwt") && !jwtToken.trim()) {
        setLoading(false);
        setError(
          "JWT token is required for /api/patients. In preview deployments it can be auto-issued; otherwise generate one via scripts/gen_dev_jwt.py."
        );
        return;
      }
    }

    const conditionList = conditions
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const bearerToken = (
      window.localStorage.getItem("ctmatch.jwt") ?? jwtToken
    ).trim();
    window.localStorage.setItem("ctmatch.jwt", bearerToken);

    try {
      const patientResponse = await fetch(`${API_BASE}/api/patients`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${bearerToken}`,
        },
        body: JSON.stringify({
          profile_json: {
            demographics: {
              age: parsedAge,
              sex,
            },
            conditions: conditionList,
          },
          source: "manual",
        }),
      });
      const patientPayload =
        (await patientResponse.json()) as CreatePatientResponse;
      if (!patientResponse.ok || !patientPayload.ok || !patientPayload.data?.id) {
        throw new Error(patientPayload.error?.message || "Failed to create patient");
      }

      const matchResponse = await fetch(`${API_BASE}/api/match`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${bearerToken}`,
        },
        body: JSON.stringify({
          patient_profile_id: patientPayload.data.id,
          top_k: parsedTopK,
          filters: {
            condition: conditionList[0] || "",
            status,
            phase,
          },
        }),
      });
      const matchPayload = (await matchResponse.json()) as CreateMatchResponse;
      if (!matchResponse.ok || !matchPayload.ok || !matchPayload.data?.match_id) {
        throw new Error(matchPayload.error?.message || "Failed to create match");
      }

      await router.push(`/matches/${matchPayload.data.match_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <header className="page-header">
        <span className="kicker">Patient Matching</span>
        <h1 className="title">Create patient profile and run matching</h1>
        <p className="subtitle">
          Provide minimum demographics and conditions. The system creates a
          patient profile, runs matching, and shows explainable checklist
          results.
        </p>
      </header>

      <section className="card">
        <form className="search-panel" onSubmit={onSubmit}>
          <div className="meta-row">
            <button
              type="button"
              className="link-button"
              onClick={() => setShowAuthAdvanced((value) => !value)}
            >
              {showAuthAdvanced ? "Hide advanced auth" : "Advanced auth"}
            </button>
          </div>

          {showAuthAdvanced && (
            <div className="field">
              <label htmlFor="jwt">JWT Token (advanced)</label>
              <input
                id="jwt"
                value={jwtToken}
                onChange={(event) => setJwtToken(event.target.value)}
                placeholder="Paste token if preview auto-auth is disabled"
              />
            </div>
          )}

          <div className="field">
            <label htmlFor="age">Age</label>
            <input
              id="age"
              type="number"
              min={0}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="sex">Sex</label>
            <select
              id="sex"
              value={sex}
              onChange={(event) => setSex(event.target.value)}
            >
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="conditions">Conditions (comma separated)</label>
            <input
              id="conditions"
              value={conditions}
              onChange={(event) => setConditions(event.target.value)}
              placeholder="e.g. leukemia, breast cancer"
            />
            {conditionSuggestions.length > 0 && (
              <div className="suggestions">
                <span className="suggestions-label">Try:</span>
                <div className="pills">
                  {conditionSuggestions.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className="pill pill-button"
                      onClick={() => setConditions(value)}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor="status">Trial Status</label>
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
            <label htmlFor="phase">Trial Phase</label>
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

          <div className="field">
            <label htmlFor="top_k">Top K</label>
            <input
              id="top_k"
              type="number"
              min={1}
              max={50}
              value={topK}
              onChange={(event) => setTopK(event.target.value)}
            />
          </div>

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Running matching..." : "Run match"}
          </button>
        </form>
      </section>

      <div className="meta-row">
        <Link href="/" className="button secondary">
          Back to trial browse
        </Link>
        {error && <span className="notice">{error}</span>}
      </div>
    </main>
  );
}
