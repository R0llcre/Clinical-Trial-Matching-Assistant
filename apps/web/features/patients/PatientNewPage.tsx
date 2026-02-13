import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, Save, UserPlus } from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Field } from "../../components/ui/Field";
import { Input } from "../../components/ui/Input";
import { Pill } from "../../components/ui/Pill";
import { Select } from "../../components/ui/Select";
import { Toast } from "../../components/ui/Toast";
import { ApiError } from "../../lib/http/client";
import { ensureSession, withSessionRetry } from "../../lib/session/session";

import { createPatient } from "./api";
import type { PatientProfileJson } from "./types";
import styles from "./PatientNewPage.module.css";

const parseList = (value: string): string[] => {
  return value
    .split(/[\n,]+/g)
    .map((entry) => entry.trim())
    .filter(Boolean);
};

export default function PatientNewPage() {
  const router = useRouter();

  const [sessionStatus, setSessionStatus] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");

  const [age, setAge] = useState("45");
  const [sex, setSex] = useState("female");
  const [conditions, setConditions] = useState("Breast Cancer");
  const [history, setHistory] = useState("");
  const [medications, setMedications] = useState("");
  const [procedures, setProcedures] = useState("");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const profileJson: PatientProfileJson = useMemo(() => {
    const ageValue = Number(age);
    const conditionList = parseList(conditions);
    const historyList = parseList(history);
    const medicationList = parseList(medications);
    const procedureList = parseList(procedures);

    const payload: PatientProfileJson = {
      demographics: {
        age: Number.isFinite(ageValue) ? ageValue : 0,
        sex: sex.trim(),
      },
    };

    if (conditionList.length > 0) {
      payload.conditions = conditionList;
    }
    if (historyList.length > 0) {
      payload.history = historyList;
    }
    if (medicationList.length > 0) {
      payload.medications = medicationList;
    }
    if (procedureList.length > 0) {
      payload.procedures = procedureList;
    }

    return payload;
  }, [age, conditions, history, medications, procedures, sex]);

  const validate = (): boolean => {
    const nextErrors: Record<string, string> = {};
    const parsedAge = Number(age);
    if (!Number.isFinite(parsedAge) || parsedAge < 0) {
      nextErrors.age = "Age must be a number >= 0.";
    }
    if (!sex.trim()) {
      nextErrors.sex = "Sex is required.";
    }
    if (parseList(conditions).length === 0) {
      nextErrors.conditions = "Add at least one condition/diagnosis.";
    }

    setFieldErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const onSubmit = async () => {
    if (loading) {
      return;
    }
    setError(null);
    if (!validate()) {
      return;
    }

    setLoading(true);
    try {
      const patient = await withSessionRetry(
        (token) => createPatient({ token, profileJson, source: "manual" }),
        {
          envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
          allowPreviewIssue: true,
        }
      );
      await router.push(`/patients/${patient.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to create patient");
      }
    } finally {
      setLoading(false);
    }
  };

  const previewConditions = profileJson.conditions ?? [];
  const previewHistory = profileJson.history ?? [];
  const previewMedications = profileJson.medications ?? [];
  const previewProcedures = profileJson.procedures ?? [];

  return (
    <Shell
      className={styles.page}
      kicker="Patients hub"
      title="New patient"
      subtitle="Create a patient profile once, then run matching and revisit history later."
      actions={
        <Link href="/patients" className="ui-button ui-button--ghost ui-button--md">
          <span className="ui-button__icon" aria-hidden="true">
            <ChevronLeft size={18} />
          </span>
          <span className="ui-button__label">Back to patients</span>
        </Link>
      }
    >
      {sessionStatus === "unavailable" ? (
        <Toast
          tone="warning"
          title="Session unavailable"
          description="This preview could not start an authenticated session. You can still browse trials, but patient features may not work."
        />
      ) : null}
      {error ? (
        <Toast tone="danger" title="Could not create patient" description={error} />
      ) : null}

      <div className={styles.layout}>
        <Card className={styles.formCard}>
          <div className={styles.formGrid}>
            <Field
              label="Age"
              htmlFor="patient-age"
              error={fieldErrors.age}
              hint="Enter age in years."
            >
              <Input
                id="patient-age"
                inputMode="numeric"
                value={age}
                invalid={Boolean(fieldErrors.age)}
                onChange={(event) => setAge(event.target.value)}
                placeholder="45"
              />
            </Field>

            <Field
              label="Sex"
              htmlFor="patient-sex"
              error={fieldErrors.sex}
              hint="Used for eligibility criteria."
            >
              <Select
                id="patient-sex"
                value={sex}
                onChange={(event) => setSex(event.target.value)}
                invalid={Boolean(fieldErrors.sex)}
              >
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other / unspecified</option>
              </Select>
            </Field>
          </div>

          <Field
            label="Conditions / diagnoses"
            htmlFor="patient-conditions"
            error={fieldErrors.conditions}
            hint="Comma or newline separated. The first condition will be used as the default match condition."
          >
            <textarea
              id="patient-conditions"
              className={`ui-input ${styles.textarea} ${fieldErrors.conditions ? "ui-input--invalid" : ""}`}
              value={conditions}
              onChange={(event) => setConditions(event.target.value)}
              placeholder="Breast Cancer"
            />
          </Field>

          <Field
            label="History (optional)"
            htmlFor="patient-history"
            hint="Comma or newline separated. Keep it high-level (no personal identifiers)."
          >
            <textarea
              id="patient-history"
              className={`ui-input ${styles.textarea}`}
              value={history}
              onChange={(event) => setHistory(event.target.value)}
              placeholder="hypertension"
            />
          </Field>

          <Field
            label="Medications (optional)"
            htmlFor="patient-medications"
            hint="Comma or newline separated."
          >
            <textarea
              id="patient-medications"
              className={`ui-input ${styles.textarea}`}
              value={medications}
              onChange={(event) => setMedications(event.target.value)}
              placeholder="metformin"
            />
          </Field>

          <Field
            label="Procedures (optional)"
            htmlFor="patient-procedures"
            hint="Comma or newline separated."
          >
            <textarea
              id="patient-procedures"
              className={`ui-input ${styles.textarea}`}
              value={procedures}
              onChange={(event) => setProcedures(event.target.value)}
              placeholder="biopsy"
            />
          </Field>

          <div className={styles.actions}>
            <Button
              tone="primary"
              size="md"
              onClick={onSubmit}
              disabled={loading || sessionStatus === "unavailable"}
              iconLeft={<UserPlus size={18} aria-hidden="true" />}
              iconRight={<Save size={18} aria-hidden="true" />}
            >
              {loading ? "Creating..." : "Create patient"}
            </Button>
            <Link href="/patients" className="ui-button ui-button--ghost ui-button--md">
              Cancel
            </Link>
          </div>
        </Card>

        <Card className={styles.previewCard}>
          <h3 className={styles.previewTitle}>Preview</h3>
          <div className={styles.previewBody}>
            <div className={styles.previewPills}>
              <Pill tone="neutral">
                Age {Number.isFinite(Number(age)) ? Math.trunc(Number(age)) : "?"}
              </Pill>
              <Pill tone="neutral">{sex.trim() || "sex?"}</Pill>
              <Pill tone="brand">{previewConditions.length} conditions</Pill>
            </div>

            {previewConditions.length > 0 ? (
              <div>
                <strong>Conditions</strong>
                <ul className={styles.previewList}>
                  {previewConditions.slice(0, 5).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {previewHistory.length > 0 ? (
              <div>
                <strong>History</strong>
                <ul className={styles.previewList}>
                  {previewHistory.slice(0, 4).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {previewMedications.length > 0 ? (
              <div>
                <strong>Medications</strong>
                <ul className={styles.previewList}>
                  {previewMedications.slice(0, 4).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {previewProcedures.length > 0 ? (
              <div>
                <strong>Procedures</strong>
                <ul className={styles.previewList}>
                  {previewProcedures.slice(0, 4).map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div style={{ color: "var(--muted)", fontSize: 13 }}>
              Patient data is stored in the preview database and scoped to your
              current browser token. Do not enter real PHI.
            </div>
          </div>
        </Card>
      </div>
    </Shell>
  );
}
