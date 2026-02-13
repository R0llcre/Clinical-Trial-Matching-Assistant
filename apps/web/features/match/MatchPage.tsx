import Link from "next/link";
import { useRouter } from "next/router";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  KeyRound,
  SlidersHorizontal,
  Stethoscope,
  User,
} from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Field } from "../../components/ui/Field";
import { Input } from "../../components/ui/Input";
import { Pill } from "../../components/ui/Pill";
import { Select } from "../../components/ui/Select";
import { Toast } from "../../components/ui/Toast";
import { API_BASE, fetchJson } from "../../lib/http/client";
import {
  clearSessionToken,
  ensureSession as ensureSessionToken,
  getSessionToken,
  setSessionToken,
} from "../../lib/session/session";
import styles from "./MatchPage.module.css";

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

type DemoProfile = {
  label: string;
  age: string;
  sex: string;
  conditions: string;
  status: string;
  phase: string;
  history?: string[];
  medications?: string[];
  procedures?: string[];
  topK?: string;
};

const DEMO_PROFILES: DemoProfile[] = [
  {
    label: "Breast cancer (female, 45)",
    age: "45",
    sex: "female",
    conditions: "Breast Cancer",
    status: "RECRUITING",
    phase: "",
    history: ["hypertension"],
    medications: ["tamoxifen"],
    procedures: ["biopsy"],
  },
  {
    label: "Advanced melanoma (male, 62)",
    age: "62",
    sex: "male",
    conditions: "Melanoma",
    status: "RECRUITING",
    phase: "",
    history: ["sun exposure"],
    medications: ["pembrolizumab"],
    procedures: ["imaging"],
  },
  {
    label: "Long COVID (female, 38)",
    age: "38",
    sex: "female",
    conditions: "Long COVID",
    status: "",
    phase: "",
    history: ["fatigue"],
    medications: ["albuterol"],
    procedures: ["pulmonary rehab"],
  },
  {
    label: "Heart failure (male, 58)",
    age: "58",
    sex: "male",
    conditions: "Heart Failure",
    status: "RECRUITING",
    phase: "",
    history: ["hypertension"],
    medications: ["beta blocker"],
    procedures: ["echocardiogram"],
  },
  {
    label: "Asthma (female, 13)",
    age: "13",
    sex: "female",
    conditions: "Asthma",
    status: "RECRUITING",
    phase: "",
    history: ["allergic rhinitis"],
    medications: ["inhaled corticosteroid"],
    procedures: ["spirometry"],
  },
  {
    label: "Rheumatoid arthritis (female, 35)",
    age: "35",
    sex: "female",
    conditions: "Rheumatoid Arthritis",
    status: "",
    phase: "",
    history: ["joint pain"],
    medications: ["methotrexate"],
    procedures: ["physical therapy"],
  },
  {
    label: "Type 2 diabetes (male, 55)",
    age: "55",
    sex: "male",
    conditions: "Type 2 Diabetes",
    status: "RECRUITING",
    phase: "",
    history: ["obesity"],
    medications: ["metformin"],
    procedures: ["diet counseling"],
  },
  {
    label: "Chronic kidney disease (male, 67)",
    age: "67",
    sex: "male",
    conditions: "Chronic Kidney Disease",
    status: "RECRUITING",
    phase: "",
    history: ["hypertension"],
    medications: ["ace inhibitor"],
    procedures: ["renal ultrasound"],
  },
  {
    label: "Leukemia (female, 29)",
    age: "29",
    sex: "female",
    conditions: "Leukemia",
    status: "RECRUITING",
    phase: "",
    history: ["anemia"],
    medications: ["cytarabine"],
    procedures: ["bone marrow biopsy"],
  },
];

type StepId = "demographics" | "conditions" | "preferences" | "review";

const STEPS: Array<{
  id: StepId;
  label: string;
  icon: ReactNode;
  blurb: string;
}> = [
  {
    id: "demographics",
    label: "Demographics",
    icon: <User size={18} aria-hidden="true" />,
    blurb: "Age and sex are enough to start. Add more later.",
  },
  {
    id: "conditions",
    label: "Conditions",
    icon: <Stethoscope size={18} aria-hidden="true" />,
    blurb: "Add the main condition(s) you want to match against.",
  },
  {
    id: "preferences",
    label: "Preferences",
    icon: <SlidersHorizontal size={18} aria-hidden="true" />,
    blurb: "Narrow trials by status/phase and choose how many to review.",
  },
  {
    id: "review",
    label: "Review & run",
    icon: <ClipboardCheck size={18} aria-hidden="true" />,
    blurb: "Run matching and review an explainable checklist per trial.",
  },
];

const parseConditionList = (value: string) => {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
};

export default function MatchPage() {
  const router = useRouter();
  const queryPrefillAppliedRef = useRef(false);

  const [step, setStep] = useState<StepId>("demographics");

  const [demo, setDemo] = useState("");
  const [age, setAge] = useState("45");
  const [sex, setSex] = useState("female");
  const [conditions, setConditions] = useState("Leukemia");
  const [demoHistory, setDemoHistory] = useState<string[]>([]);
  const [demoMedications, setDemoMedications] = useState<string[]>([]);
  const [demoProcedures, setDemoProcedures] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [phase, setPhase] = useState("");
  const [topK, setTopK] = useState("10");

  const [conditionSuggestions, setConditionSuggestions] = useState<string[]>([]);

  const [sessionStatus, setSessionStatus] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");
  const [debugToken, setDebugToken] = useState(
    process.env.NEXT_PUBLIC_DEV_JWT ?? ""
  );

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const showAuthDebug = useMemo(() => {
    const envEnabled = process.env.NEXT_PUBLIC_SHOW_AUTH_DEBUG === "1";
    if (!router.isReady) {
      return envEnabled;
    }
    const debugParam =
      typeof router.query.debug === "string" ? router.query.debug : "";
    return envEnabled || debugParam === "1";
  }, [router.isReady, router.query.debug]);

  const stepIndex = STEPS.findIndex((item) => item.id === step);

  const postWithSessionRetry = async <T,>(
    url: string,
    body: unknown
  ): Promise<{ response: Response; payload: T | null }> => {
    const doPost = async (token: string) => {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
    };

    const initialToken = getSessionToken();
    let response = await doPost(initialToken);

    if (response.status === 401) {
      clearSessionToken();
      const refreshed = await ensureSession();
      const nextToken = getSessionToken() || refreshed;
      if (nextToken && nextToken !== initialToken) {
        response = await doPost(nextToken);
      }
    }

    let payload: T | null = null;
    try {
      payload = (await response.json()) as T;
    } catch {
      payload = null;
    }
    return { response, payload };
  };

  const ensureSession = async () => {
    setSessionStatus("loading");
    const { token, status } = await ensureSessionToken({
      envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
      allowPreviewIssue: true,
    });
    setSessionStatus(status);
    if (token) {
      setDebugToken(token);
    }
    return token;
  };

  useEffect(() => {
    void ensureSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!router.isReady || queryPrefillAppliedRef.current) {
      return;
    }
    queryPrefillAppliedRef.current = true;

    const prefill = router.query.condition;
    if (typeof prefill === "string" && prefill.trim()) {
      setConditions(prefill.trim());
      setStep("conditions");
    }
  }, [router.isReady, router.query.condition]);

  useEffect(() => {
    void (async () => {
      try {
        const { response, payload } = await fetchJson<{
          trials: TrialForSuggestions[];
        }>(`${API_BASE}/api/trials?page=1&page_size=50`);
        if (!response.ok || !payload?.ok) {
          return;
        }
        const trials = payload.data?.trials ?? [];

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

  const applyDemo = (value: string) => {
    const selected = DEMO_PROFILES.find((profile) => profile.label === value);
    if (!selected) {
      setDemoHistory([]);
      setDemoMedications([]);
      setDemoProcedures([]);
      return;
    }
    setAge(selected.age);
    setSex(selected.sex);
    setConditions(selected.conditions);
    setDemoHistory(selected.history ?? []);
    setDemoMedications(selected.medications ?? []);
    setDemoProcedures(selected.procedures ?? []);
    setStatus(selected.status);
    setPhase(selected.phase);
    if (selected.topK) {
      setTopK(selected.topK);
    }
  };

  const validateDemographics = () => {
    const nextErrors: Record<string, string> = {};
    const parsedAge = Number(age);
    if (!Number.isFinite(parsedAge) || Number.isNaN(parsedAge) || parsedAge < 0) {
      nextErrors.age = "Enter a valid age (0+).";
    }
    if (!sex.trim()) {
      nextErrors.sex = "Select a sex value.";
    }

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const validateConditions = () => {
    const nextErrors: Record<string, string> = {};
    const list = parseConditionList(conditions);
    if (list.length === 0) {
      nextErrors.conditions = "Add at least one condition.";
    }
    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const validatePreferences = () => {
    const nextErrors: Record<string, string> = {};
    const parsedTopK = Number(topK);
    if (
      !Number.isFinite(parsedTopK) ||
      Number.isNaN(parsedTopK) ||
      parsedTopK < 1 ||
      parsedTopK > 50
    ) {
      nextErrors.topK = "Top K must be between 1 and 50.";
    }
    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const canAdvance = () => {
    if (step === "demographics") {
      return validateDemographics();
    }
    if (step === "conditions") {
      return validateConditions();
    }
    if (step === "preferences") {
      return validatePreferences();
    }
    return true;
  };

  const goNext = () => {
    setError(null);
    if (!canAdvance()) {
      return;
    }
    const next = STEPS[stepIndex + 1];
    if (next) {
      setStep(next.id);
    }
  };

  const goBack = () => {
    setError(null);
    setFieldErrors({});
    const prev = STEPS[stepIndex - 1];
    if (prev) {
      setStep(prev.id);
    }
  };

  const runMatch = async () => {
    setLoading(true);
    setError(null);

    if (!validateDemographics()) {
      setLoading(false);
      setStep("demographics");
      return;
    }
    if (!validateConditions()) {
      setLoading(false);
      setStep("conditions");
      return;
    }
    if (!validatePreferences()) {
      setLoading(false);
      setStep("preferences");
      return;
    }

    const parsedAge = Number(age);
    const parsedTopK = Number(topK);
    const conditionList = parseConditionList(conditions);

    const token = getSessionToken();
    if (!token) {
      const refreshed = await ensureSession();
      if (!refreshed) {
        setLoading(false);
        setSessionStatus("unavailable");
        setError(
          "This preview could not start an authenticated session automatically. Try again, or open debug mode to paste a token."
        );
        return;
      }
    }

    const bearerToken = getSessionToken();
    if (!bearerToken) {
      setLoading(false);
      setError(
        "Session unavailable. Refresh the page, or open debug mode to paste a token."
      );
      return;
    }

    try {
      const profileJson: Record<string, unknown> = {
        demographics: {
          age: parsedAge,
          sex,
        },
        conditions: conditionList,
      };
      if (demoHistory.length > 0) {
        profileJson.history = demoHistory;
      }
      if (demoMedications.length > 0) {
        profileJson.medications = demoMedications;
      }
      if (demoProcedures.length > 0) {
        profileJson.procedures = demoProcedures;
      }

      const { response: patientResponse, payload: patientPayload } =
        await postWithSessionRetry<CreatePatientResponse>(`${API_BASE}/api/patients`, {
          profile_json: profileJson,
          source: "manual",
        });
      if (!patientResponse.ok || !patientPayload.ok || !patientPayload.data?.id) {
        throw new Error(patientPayload.error?.message || "Failed to create patient");
      }

      const { response: matchResponse, payload: matchPayload } =
        await postWithSessionRetry<CreateMatchResponse>(`${API_BASE}/api/match`, {
          patient_profile_id: patientPayload.data.id,
          top_k: parsedTopK,
          filters: {
            condition: conditionList[0] || "",
            status,
            phase,
          },
        });
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

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (step !== "review") {
      goNext();
      return;
    }
    await runMatch();
  };

  const reviewConditions = parseConditionList(conditions);

  return (
    <Shell
      className={styles.page}
      kicker="Patient matching"
      title="Match a patient to clinical trials"
      subtitle="Create a lightweight patient profile and generate an explainable checklist per trial."
      actions={
        <>
          <Link href="/" className="ui-button ui-button--ghost ui-button--md">
            Browse trials
          </Link>
        </>
      }
    >
      {sessionStatus === "unavailable" ? (
        <Toast
          tone="warning"
          title="Session unavailable"
          description={
            showAuthDebug
              ? "Preview auto-session is not available. Paste a token below (debug mode)."
              : "Preview auto-session is not available. You can still browse trials."
          }
        />
      ) : null}

      {error ? (
        <Toast
          tone="danger"
          title="Unable to run matching"
          description={error}
        />
      ) : null}

      <form onSubmit={onSubmit} className="match-stepper">
        <div className="match-steps">
          {STEPS.map((item, index) => {
            const active = item.id === step;
            const done = index < stepIndex;
            const clickable = index <= stepIndex;
            return (
              <button
                key={item.id}
                type="button"
                className={`match-step ${active ? "is-active" : ""} ${
                  done ? "is-done" : ""
                }`}
                onClick={() => {
                  if (!clickable) {
                    return;
                  }
                  setError(null);
                  setFieldErrors({});
                  setStep(item.id);
                }}
                disabled={!clickable}
              >
                <span className="match-step__index" aria-hidden="true">
                  {done ? <CheckCircle2 size={18} /> : index + 1}
                </span>
                <span className="match-step__body">
                  <span className="match-step__label">
                    {item.icon}
                    {item.label}
                  </span>
                  <span className="match-step__blurb">{item.blurb}</span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="match-panel">
          {step === "demographics" ? (
            <Card className="match-card">
              <div className="match-card__title">Demographics</div>
              <div className="match-card__grid">
                <Field
                  label="Demo profile"
                  htmlFor="demo"
                  hint="Optional preset to get started quickly. Presets include synthetic history, medication, and procedure context."
                >
                  <Select
                    id="demo"
                    value={demo}
                    onChange={(event) => {
                      const value = event.target.value;
                      setDemo(value);
                      applyDemo(value);
                    }}
                  >
                    <option value="">Choose a preset...</option>
                    {DEMO_PROFILES.map((profile) => (
                      <option key={profile.label} value={profile.label}>
                        {profile.label}
                      </option>
                    ))}
                  </Select>
                </Field>

                <div className="match-card__row">
                  <Field
                    label="Age"
                    htmlFor="age"
                    error={fieldErrors.age}
                  >
                    <Input
                      id="age"
                      type="number"
                      min={0}
                      value={age}
                      onChange={(event) => setAge(event.target.value)}
                      invalid={Boolean(fieldErrors.age)}
                    />
                  </Field>
                  <Field
                    label="Sex"
                    htmlFor="sex"
                    error={fieldErrors.sex}
                  >
                    <Select
                      id="sex"
                      value={sex}
                      onChange={(event) => setSex(event.target.value)}
                      invalid={Boolean(fieldErrors.sex)}
                    >
                      <option value="female">Female</option>
                      <option value="male">Male</option>
                      <option value="other">Other</option>
                    </Select>
                  </Field>
                </div>
              </div>
            </Card>
          ) : null}

          {step === "conditions" ? (
            <Card className="match-card">
              <div className="match-card__title">Conditions</div>
              <div className="match-card__grid">
                <Field
                  label="Conditions"
                  htmlFor="conditions"
                  hint="Comma-separated. The first condition is used as the primary match filter."
                  error={fieldErrors.conditions}
                >
                  <Input
                    id="conditions"
                    value={conditions}
                    onChange={(event) => setConditions(event.target.value)}
                    placeholder="e.g. leukemia, breast cancer"
                    invalid={Boolean(fieldErrors.conditions)}
                  />
                </Field>

                {conditionSuggestions.length > 0 ? (
                  <div className="match-suggestions">
                    <div className="match-suggestions__label">Popular conditions</div>
                    <div className="match-suggestions__chips">
                      {conditionSuggestions.map((value) => (
                        <button
                          key={value}
                          type="button"
                          className="match-chip ui-pill ui-pill--neutral"
                          onClick={() => setConditions(value)}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </Card>
          ) : null}

          {step === "preferences" ? (
            <Card className="match-card">
              <div className="match-card__title">Preferences</div>
              <div className="match-card__grid">
                <div className="match-card__row">
                  <Field label="Trial status" htmlFor="status">
                    <Select
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
                    </Select>
                  </Field>
                  <Field label="Trial phase" htmlFor="phase">
                    <Select
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
                    </Select>
                  </Field>
                </div>

                <Field
                  label="Top K"
                  htmlFor="top_k"
                  hint="How many trials to include in the result set."
                  error={fieldErrors.topK}
                >
                  <Input
                    id="top_k"
                    type="number"
                    min={1}
                    max={50}
                    value={topK}
                    onChange={(event) => setTopK(event.target.value)}
                    invalid={Boolean(fieldErrors.topK)}
                  />
                </Field>
              </div>
            </Card>
          ) : null}

          {step === "review" ? (
            <Card className="match-card">
              <div className="match-card__title">Review</div>

              <div className="match-review">
                <div className="match-review__grid">
                  <div className="match-review__block">
                    <div className="match-review__label">Demographics</div>
                    <div className="match-review__value">
                      Age <strong>{age}</strong> · Sex <strong>{sex}</strong>
                    </div>
                  </div>
                  <div className="match-review__block">
                    <div className="match-review__label">Conditions</div>
                    <div className="match-review__pills">
                      {reviewConditions.length > 0 ? (
                        reviewConditions.map((value) => (
                          <Pill key={value} tone="neutral">
                            {value}
                          </Pill>
                        ))
                      ) : (
                        <Pill tone="warning">None</Pill>
                      )}
                    </div>
                  </div>
                  {demoHistory.length > 0 ||
                  demoMedications.length > 0 ||
                  demoProcedures.length > 0 ? (
                    <div className="match-review__block">
                      <div className="match-review__label">Synthetic context</div>
                      <div className="match-review__pills">
                        {demoHistory.map((value) => (
                          <Pill key={`history-${value}`} tone="info">
                            history: {value}
                          </Pill>
                        ))}
                        {demoMedications.map((value) => (
                          <Pill key={`med-${value}`} tone="brand">
                            medication: {value}
                          </Pill>
                        ))}
                        {demoProcedures.map((value) => (
                          <Pill key={`proc-${value}`} tone="neutral">
                            procedure: {value}
                          </Pill>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="match-review__block">
                    <div className="match-review__label">Filters</div>
                    <div className="match-review__pills">
                      {status ? <Pill tone="brand">{status}</Pill> : <Pill tone="neutral">any status</Pill>}
                      {phase ? <Pill tone="brand">{phase}</Pill> : <Pill tone="neutral">any phase</Pill>}
                      <Pill tone="warning">top {topK}</Pill>
                    </div>
                  </div>
                </div>

                {showAuthDebug ? (
                  <Card tone="subtle" className="match-auth-debug">
                    <div className="match-auth-debug__title">
                      <KeyRound size={18} aria-hidden="true" />
                      Auth (debug)
                    </div>
                    <div className="match-auth-debug__body">
                      <Field
                        label="Authorization token (JWT)"
                        htmlFor="debug_token"
                        hint="Only needed if preview auto-session is disabled."
                      >
                        <Input
                          id="debug_token"
                          value={debugToken}
                          onChange={(event) => {
                            const value = event.target.value;
                            setDebugToken(value);
                            if (value.trim()) {
                              setSessionToken(value.trim());
                              setSessionStatus("ready");
                            } else {
                              clearSessionToken();
                              setSessionStatus("unavailable");
                            }
                          }}
                          placeholder="Paste token if needed"
                        />
                      </Field>
                    </div>
                  </Card>
                ) : null}

                {sessionStatus !== "ready" ? (
                  <div className="match-warning">
                    <AlertTriangle size={18} aria-hidden="true" />
                    <span>
                      Session is not ready. Matching may fail in environments without preview auth.
                    </span>
                  </div>
                ) : null}
              </div>

              {reviewConditions.length === 0 ? (
                <EmptyState
                  title="Add a condition to run matching"
                  description="Go back one step and add at least one condition."
                  icon={<AlertTriangle size={22} />}
                />
              ) : null}
            </Card>
          ) : null}

          <div className="match-nav">
            <button
              type="button"
              className="ui-button ui-button--ghost ui-button--md"
              onClick={goBack}
              disabled={stepIndex === 0 || loading}
            >
              Back
            </button>
            {step !== "review" ? (
              <button
                type="button"
                className="ui-button ui-button--primary ui-button--md"
                onClick={goNext}
                disabled={loading}
              >
                Next
                <span className="ui-button__icon" aria-hidden="true">
                  <ArrowRight size={18} />
                </span>
              </button>
            ) : (
              <button
                type="submit"
                className="ui-button ui-button--primary ui-button--md"
                disabled={loading || reviewConditions.length === 0}
              >
                {loading ? "Running..." : "Run match"}
                <span className="ui-button__icon" aria-hidden="true">
                  <ArrowRight size={18} />
                </span>
              </button>
            )}
          </div>
        </div>
      </form>

      <div className="match-footer-links">
        <Link href="/" className="match-footer-links__link">
          Browse trials
        </Link>
        <a
          className="match-footer-links__link"
          href={`${API_BASE.replace(/\/+$/, "")}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          API docs
        </a>
      </div>
    </Shell>
  );
}
