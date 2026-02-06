import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { useState } from "react";

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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function MatchPage() {
  const router = useRouter();
  const [age, setAge] = useState("52");
  const [sex, setSex] = useState("female");
  const [conditions, setConditions] = useState("type 2 diabetes");
  const [status, setStatus] = useState("RECRUITING");
  const [phase, setPhase] = useState("");
  const [topK, setTopK] = useState("10");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

    const conditionList = conditions
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    try {
      const patientResponse = await fetch(`${API_BASE}/api/patients`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
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
        headers: {"Content-Type": "application/json"},
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
              placeholder="e.g. diabetes, hypertension"
            />
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
