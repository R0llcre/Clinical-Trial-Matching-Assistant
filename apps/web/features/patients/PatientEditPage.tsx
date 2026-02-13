import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, PencilLine, Plus, Save, Trash2 } from "lucide-react";

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
import { isHiddenText } from "../../lib/profile/hidden";
import { ensureSession, withSessionRetry } from "../../lib/session/session";

import { getPatient, updatePatient } from "./api";
import type {
  Patient,
  PatientLabEntry,
  PatientNamedDateEntry,
  PatientProfileJson,
  PatientTimelineEntry,
} from "./types";
import styles from "./PatientEditPage.module.css";

type TimelineRow = { name: string; date: string };
type LabRow = { name: string; value: string; date: string };

const parseList = (value: string): string[] => {
  return value
    .split(/[\n,]+/g)
    .map((entry) => entry.trim())
    .filter(Boolean);
};

const normalizeText = (value: unknown): string => {
  return typeof value === "string" ? value.trim() : "";
};

const safeDate = (value: unknown): string => {
  if (typeof value !== "string") {
    return "";
  }
  const trimmed = value.trim();
  return trimmed.length >= 10 ? trimmed.slice(0, 10) : trimmed;
};

const timelineRowsFromEntries = (
  entries: PatientTimelineEntry[] | undefined
): TimelineRow[] => {
  const rows: TimelineRow[] = [];
  for (const entry of entries ?? []) {
    if (typeof entry === "string") {
      const name = entry.trim();
      if (name) {
        rows.push({ name, date: "" });
      }
      continue;
    }
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const maybe = entry as PatientNamedDateEntry;
    const name = normalizeText(maybe.name);
    const date = safeDate(maybe.date);
    if (name) {
      rows.push({ name, date });
    }
  }
  return rows.length > 0 ? rows : [{ name: "", date: "" }];
};

const timelineEntriesFromRows = (rows: TimelineRow[]): PatientTimelineEntry[] => {
  const entries: PatientTimelineEntry[] = [];
  for (const row of rows) {
    const name = row.name.trim();
    const date = row.date.trim();
    if (!name) {
      continue;
    }
    if (date) {
      entries.push({ name, date });
    } else {
      entries.push(name);
    }
  }
  return entries;
};

const labRowsFromProfile = (labs: unknown): LabRow[] => {
  const rows: LabRow[] = [];
  if (Array.isArray(labs)) {
    for (const entry of labs) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const maybe = entry as Record<string, unknown>;
      const name = normalizeText(maybe.name);
      const valueRaw = maybe.value;
      const value =
        typeof valueRaw === "number" && Number.isFinite(valueRaw)
          ? String(valueRaw)
          : typeof valueRaw === "string"
            ? valueRaw.trim()
            : "";
      const date = safeDate(maybe.date);
      if (name) {
        rows.push({ name, value, date });
      }
    }
  } else if (labs && typeof labs === "object") {
    for (const [key, val] of Object.entries(labs as Record<string, unknown>)) {
      const name = normalizeText(key);
      const value =
        typeof val === "number" && Number.isFinite(val) ? String(val) : "";
      if (name && value) {
        rows.push({ name, value, date: "" });
      }
    }
  }
  return rows.length > 0 ? rows : [{ name: "", value: "", date: "" }];
};

const labEntriesFromRows = (rows: LabRow[]): PatientLabEntry[] => {
  const entries: PatientLabEntry[] = [];
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) {
      continue;
    }
    const parsedValue = Number(row.value);
    if (!Number.isFinite(parsedValue)) {
      continue;
    }
    const date = row.date.trim();
    entries.push(date ? { name, value: parsedValue, date } : { name, value: parsedValue });
  }
  return entries;
};

type FocusSection =
  | "demographics"
  | "conditions"
  | "history"
  | "medications"
  | "procedures"
  | "labs"
  | "other"
  | "";

const sectionFromFocus = (value: string): FocusSection => {
  const key = value.trim().toLowerCase();
  if (!key) {
    return "";
  }
  if (key.startsWith("demographics.age") || key.includes("age")) {
    return "demographics";
  }
  if (key.startsWith("demographics.sex") || key.includes("sex")) {
    return "demographics";
  }
  if (key.startsWith("conditions")) {
    return "conditions";
  }
  if (key.startsWith("history")) {
    return "history";
  }
  if (key.startsWith("medications")) {
    return "medications";
  }
  if (key.startsWith("procedures")) {
    return "procedures";
  }
  if (key.startsWith("labs") || key.includes("lab")) {
    return "labs";
  }
  if (key.startsWith("other") || key.includes("note")) {
    return "other";
  }
  // Default unknown focus values to labs (common case: specific lab name).
  return "labs";
};

export default function PatientEditPage() {
  const router = useRouter();
  const patientId = typeof router.query.id === "string" ? router.query.id : "";
  const focusParam = typeof router.query.focus === "string" ? router.query.focus : "";

  const [sessionStatus, setSessionStatus] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");

  const [patient, setPatient] = useState<Patient | null>(null);
  const [patientLoading, setPatientLoading] = useState(true);
  const [patientError, setPatientError] = useState<string | null>(null);

  const [age, setAge] = useState("45");
  const [sex, setSex] = useState("female");
  const [conditionsText, setConditionsText] = useState("");

  const [historyRows, setHistoryRows] = useState<TimelineRow[]>([
    { name: "", date: "" },
  ]);
  const [medicationRows, setMedicationRows] = useState<TimelineRow[]>([
    { name: "", date: "" },
  ]);
  const [procedureRows, setProcedureRows] = useState<TimelineRow[]>([
    { name: "", date: "" },
  ]);
  const [labRows, setLabRows] = useState<LabRow[]>([
    { name: "", value: "", date: "" },
  ]);
  const [otherText, setOtherText] = useState("");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const focusSection = useMemo(() => sectionFromFocus(focusParam), [focusParam]);
  const [highlightSection, setHighlightSection] = useState<FocusSection>("");
  const smartFocusAppliedRef = useRef(false);

  const demographicsRef = useRef<HTMLDivElement | null>(null);
  const conditionsRef = useRef<HTMLDivElement | null>(null);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const medicationsRef = useRef<HTMLDivElement | null>(null);
  const proceduresRef = useRef<HTMLDivElement | null>(null);
  const labsRef = useRef<HTMLDivElement | null>(null);
  const otherRef = useRef<HTMLDivElement | null>(null);

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
    const load = async () => {
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

        const demo = loaded.profile_json?.demographics;
        const ageValue = typeof demo?.age === "number" ? demo.age : null;
        setAge(Number.isFinite(ageValue) ? String(Math.trunc(ageValue)) : "0");
        setSex(normalizeText(demo?.sex) || "female");

        const conditionsList = Array.isArray(loaded.profile_json?.conditions)
          ? loaded.profile_json.conditions
              .map((entry) => normalizeText(entry))
              .filter((entry) => entry && !isHiddenText(entry))
          : [];
        setConditionsText(conditionsList.join("\n"));

        setHistoryRows(timelineRowsFromEntries(loaded.profile_json?.history));
        setMedicationRows(timelineRowsFromEntries(loaded.profile_json?.medications));
        setProcedureRows(timelineRowsFromEntries(loaded.profile_json?.procedures));
        setLabRows(labRowsFromProfile(loaded.profile_json?.labs));

        const otherList = Array.isArray(loaded.profile_json?.other)
          ? loaded.profile_json.other
              .map((entry) => normalizeText(entry))
              .filter((entry) => entry && !isHiddenText(entry))
          : [];
        setOtherText(otherList.join("\n"));
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

    void load();
    return () => {
      cancelled = true;
    };
  }, [patientId, router.isReady]);

  useEffect(() => {
    if (!router.isReady || !focusSection || patientLoading) {
      return;
    }

    const refMap: Record<Exclude<FocusSection, "">, React.RefObject<HTMLDivElement>> = {
      demographics: demographicsRef,
      conditions: conditionsRef,
      history: historyRef,
      medications: medicationsRef,
      procedures: proceduresRef,
      labs: labsRef,
      other: otherRef,
    };
    const targetRef = refMap[focusSection];
    if (!targetRef?.current) {
      return;
    }

    setHighlightSection(focusSection);
    targetRef.current.scrollIntoView({ behavior: "smooth", block: "start" });

    if (!smartFocusAppliedRef.current) {
      smartFocusAppliedRef.current = true;

      const focusKey = focusParam.trim();
      const normalized = focusKey.toLowerCase();
      const focusLater = (id: string) => {
        window.setTimeout(() => {
          const el = document.getElementById(id);
          if (el && "focus" in el) {
            (el as HTMLElement).focus();
          }
        }, 250);
      };

      const reserved = new Set([
        "demographics.age",
        "demographics.sex",
        "age",
        "sex",
        "conditions",
        "history",
        "medications",
        "procedures",
        "labs",
        "other",
        "history_timeline",
        "medications_timeline",
        "procedures_timeline",
        "labs_timeline",
      ]);

      if (normalized === "demographics.age" || normalized === "age") {
        focusLater("patient-age");
      } else if (normalized === "demographics.sex" || normalized === "sex") {
        focusLater("patient-sex");
      } else if (normalized === "conditions") {
        focusLater("patient-conditions");
      } else if (normalized === "labs_timeline") {
        focusLater("lab-date-0");
      } else if (normalized === "history_timeline") {
        focusLater("history-date-0");
      } else if (normalized === "medications_timeline") {
        focusLater("medications-date-0");
      } else if (normalized === "procedures_timeline") {
        focusLater("procedures-date-0");
      } else if (focusSection === "labs" && normalized && !reserved.has(normalized)) {
        // Treat unknown focus values as a specific lab name (common for missing lab rules).
        const labName = focusKey.trim();
        if (labName) {
          setLabRows((prev) => {
            const current = prev.length > 0 ? [...prev] : [{ name: "", value: "", date: "" }];
            const first = current[0];
            const isFirstEmpty =
              !first?.name?.trim() && !first?.value?.trim() && !first?.date?.trim();
            if (isFirstEmpty) {
              current[0] = { ...first, name: labName };
              return current;
            }
            return [{ name: labName, value: "", date: "" }, ...current];
          });
          focusLater("lab-value-0");
        }
      }
    }

    const timer = window.setTimeout(() => setHighlightSection(""), 3500);
    return () => window.clearTimeout(timer);
  }, [focusParam, focusSection, patientLoading, router.isReady]);

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    const parsedAge = Number(age);
    if (!Number.isFinite(parsedAge) || parsedAge < 0) {
      next.age = "Age must be a number >= 0.";
    }
    if (!sex.trim()) {
      next.sex = "Sex is required.";
    }
    if (parseList(conditionsText).length === 0) {
      next.conditions = "Add at least one condition/diagnosis.";
    }

    const labHasInvalid = labRows.some((row) => {
      if (!row.name.trim()) {
        return false;
      }
      const parsed = Number(row.value);
      return !Number.isFinite(parsed);
    });
    if (labHasInvalid) {
      next.labs = "Lab rows require a numeric value when a name is provided.";
    }

    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const profileJson: PatientProfileJson = useMemo(() => {
    const base = (patient?.profile_json ?? {}) as PatientProfileJson;
    const parsedAge = Number(age);
    const ageValue = Number.isFinite(parsedAge) ? parsedAge : 0;
    const conditions = parseList(conditionsText);
    const history = timelineEntriesFromRows(historyRows);
    const medications = timelineEntriesFromRows(medicationRows);
    const procedures = timelineEntriesFromRows(procedureRows);
    const labs = labEntriesFromRows(labRows);
    const other = parseList(otherText);

    const next: PatientProfileJson = {
      ...base,
      demographics: {
        age: ageValue,
        sex: sex.trim(),
      },
    };

    if (conditions.length > 0) {
      next.conditions = conditions;
    } else {
      delete next.conditions;
    }

    if (history.length > 0) {
      next.history = history;
    } else {
      delete next.history;
    }

    if (medications.length > 0) {
      next.medications = medications;
    } else {
      delete next.medications;
    }

    if (procedures.length > 0) {
      next.procedures = procedures;
    } else {
      delete next.procedures;
    }

    if (labs.length > 0) {
      next.labs = labs;
    } else {
      delete next.labs;
    }

    if (other.length > 0) {
      next.other = other;
    } else {
      delete next.other;
    }

    return next;
  }, [
    age,
    conditionsText,
    historyRows,
    labRows,
    medicationRows,
    otherText,
    patient?.profile_json,
    procedureRows,
    sex,
  ]);

  const onSave = async () => {
    if (!patientId || saving) {
      return;
    }
    setSaveError(null);
    if (!validate()) {
      return;
    }

    setSaving(true);
    try {
      const updated = await withSessionRetry(
        (token) =>
          updatePatient({
            token,
            patientId,
            profileJson,
            source: patient?.source ?? "manual",
          }),
        {
          envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
          allowPreviewIssue: true,
        }
      );
      await router.push(`/patients/${updated.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setSaveError(err.message);
      } else if (err instanceof Error) {
        setSaveError(err.message);
      } else {
        setSaveError("Failed to update patient");
      }
    } finally {
      setSaving(false);
    }
  };

  const previewConditions = profileJson.conditions ?? [];
  const previewHistory = Array.isArray(profileJson.history) ? profileJson.history : [];
  const previewLabs = Array.isArray(profileJson.labs) ? profileJson.labs : [];

  const sectionClass = (section: FocusSection) =>
    `${styles.section} ${styles.card} ${
      highlightSection === section ? styles.sectionFocused : ""
    }`;

  const renderTimelineRows = (
    rows: TimelineRow[],
    setRows: (rows: TimelineRow[]) => void,
    {
      idPrefix,
      nameLabel,
      dateLabel,
    }: { idPrefix: string; nameLabel: string; dateLabel: string }
  ) => {
    return (
      <div className={styles.rows}>
        {rows.map((row, idx) => (
          <div key={idx} className={styles.row}>
            <Field
              label={idx === 0 ? nameLabel : ""}
              htmlFor={`${idPrefix}-name-${idx}`}
            >
              <Input
                id={`${idPrefix}-name-${idx}`}
                value={row.name}
                onChange={(event) => {
                  const next = [...rows];
                  next[idx] = { ...next[idx], name: event.target.value };
                  setRows(next);
                }}
                placeholder="name"
              />
            </Field>
            <Field
              label={idx === 0 ? dateLabel : ""}
              htmlFor={`${idPrefix}-date-${idx}`}
            >
              <Input
                id={`${idPrefix}-date-${idx}`}
                type="date"
                value={row.date}
                onChange={(event) => {
                  const next = [...rows];
                  next[idx] = { ...next[idx], date: event.target.value };
                  setRows(next);
                }}
              />
            </Field>
            <div className={styles.rowActions}>
              <Button
                tone="ghost"
                size="sm"
                type="button"
                onClick={() => {
                  if (rows.length === 1) {
                    setRows([{ name: "", date: "" }]);
                    return;
                  }
                  setRows(rows.filter((_, rowIdx) => rowIdx !== idx));
                }}
                aria-label={`Remove ${nameLabel} row`}
                iconLeft={<Trash2 size={16} aria-hidden="true" />}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}

        <Button
          tone="secondary"
          size="sm"
          type="button"
          onClick={() => setRows([...rows, { name: "", date: "" }])}
          iconLeft={<Plus size={16} aria-hidden="true" />}
        >
          Add row
        </Button>
      </div>
    );
  };

  const renderLabRows = () => {
    return (
      <div className={styles.rows}>
        {labRows.map((row, idx) => (
          <div key={idx} className={`${styles.row} ${styles.rowLab}`}>
            <Field label={idx === 0 ? "Lab name" : ""} htmlFor={`lab-name-${idx}`}>
              <Input
                id={`lab-name-${idx}`}
                value={row.name}
                onChange={(event) => {
                  const next = [...labRows];
                  next[idx] = { ...next[idx], name: event.target.value };
                  setLabRows(next);
                }}
                placeholder="eosinophils"
              />
            </Field>
            <Field label={idx === 0 ? "Value" : ""} htmlFor={`lab-value-${idx}`}>
              <Input
                id={`lab-value-${idx}`}
                inputMode="decimal"
                value={row.value}
                onChange={(event) => {
                  const next = [...labRows];
                  next[idx] = { ...next[idx], value: event.target.value };
                  setLabRows(next);
                }}
                placeholder="150"
              />
            </Field>
            <Field label={idx === 0 ? "Date" : ""} htmlFor={`lab-date-${idx}`}>
              <Input
                id={`lab-date-${idx}`}
                type="date"
                value={row.date}
                onChange={(event) => {
                  const next = [...labRows];
                  next[idx] = { ...next[idx], date: event.target.value };
                  setLabRows(next);
                }}
              />
            </Field>
            <div className={styles.rowActions}>
              <Button
                tone="ghost"
                size="sm"
                type="button"
                onClick={() => {
                  if (labRows.length === 1) {
                    setLabRows([{ name: "", value: "", date: "" }]);
                    return;
                  }
                  setLabRows(labRows.filter((_, rowIdx) => rowIdx !== idx));
                }}
                aria-label="Remove lab row"
                iconLeft={<Trash2 size={16} aria-hidden="true" />}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}

        <Button
          tone="secondary"
          size="sm"
          type="button"
          onClick={() => setLabRows([...labRows, { name: "", value: "", date: "" }])}
          iconLeft={<Plus size={16} aria-hidden="true" />}
        >
          Add lab
        </Button>
      </div>
    );
  };

  return (
    <Shell
      className={styles.page}
      kicker={patient ? `Patient ${patient.id.slice(0, 8)}` : "Patients hub"}
      title="Edit patient"
      subtitle="Update missing demographics, labs, and timelines. Then rerun matching from the patient page."
      actions={
        <>
          <Link
            href={patientId ? `/patients/${encodeURIComponent(patientId)}` : "/patients"}
            className="ui-button ui-button--ghost ui-button--md"
          >
            <span className="ui-button__icon" aria-hidden="true">
              <ChevronLeft size={18} />
            </span>
            <span className="ui-button__label">Back</span>
          </Link>
          <Link href="/patients" className="ui-button ui-button--secondary ui-button--md">
            Patients
          </Link>
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
      {saveError ? (
        <Toast tone="danger" title="Could not save changes" description={saveError} />
      ) : null}

      <div className={styles.layout}>
        <div className={styles.main}>
          <div
            ref={demographicsRef}
            className={sectionClass("demographics")}
            data-section="demographics"
          >
            <div className={styles.cardHeader}>
              <div>
                <h2>Demographics</h2>
                <p>Age and sex are required for most eligibility rules.</p>
              </div>
            </div>

            {patientLoading ? (
              <div>
                <Skeleton width="long" />
                <div style={{ marginTop: 10 }}>
                  <Skeleton width="medium" />
                </div>
              </div>
            ) : (
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
            )}
          </div>

          <div
            ref={conditionsRef}
            className={sectionClass("conditions")}
            data-section="conditions"
          >
            <div className={styles.cardHeader}>
              <div>
                <h2>Conditions / diagnoses</h2>
                <p>Primary condition influences search and matching quality.</p>
              </div>
            </div>

            <Field
              label="Conditions"
              htmlFor="patient-conditions"
              error={fieldErrors.conditions}
              hint="Comma or newline separated. First condition will be used as the default match condition."
            >
              <textarea
                id="patient-conditions"
                className={`ui-input ${styles.textarea} ${fieldErrors.conditions ? "ui-input--invalid" : ""}`}
                value={conditionsText}
                onChange={(event) => setConditionsText(event.target.value)}
                placeholder="Breast Cancer"
              />
            </Field>
          </div>

          <div
            ref={historyRef}
            className={sectionClass("history")}
            data-section="history"
          >
            <div className={styles.cardHeader}>
              <div>
                <h2>History</h2>
                <p>High-level medical history items, optionally with dates.</p>
              </div>
            </div>
            {renderTimelineRows(historyRows, setHistoryRows, {
              idPrefix: "history",
              nameLabel: "History item",
              dateLabel: "Date",
            })}
            <div className={styles.rowHint}>
              Keep entries synthetic or de-identified. Avoid real PHI.
            </div>
          </div>

          <div
            ref={medicationsRef}
            className={sectionClass("medications")}
            data-section="medications"
          >
            <div className={styles.cardHeader}>
              <div>
                <h2>Medications</h2>
                <p>Current/past medications, optionally with start/end dates.</p>
              </div>
            </div>
            {renderTimelineRows(medicationRows, setMedicationRows, {
              idPrefix: "medications",
              nameLabel: "Medication",
              dateLabel: "Date",
            })}
          </div>

          <div
            ref={proceduresRef}
            className={sectionClass("procedures")}
            data-section="procedures"
          >
            <div className={styles.cardHeader}>
              <div>
                <h2>Procedures</h2>
                <p>Procedures, optionally with dates.</p>
              </div>
            </div>
            {renderTimelineRows(procedureRows, setProcedureRows, {
              idPrefix: "procedures",
              nameLabel: "Procedure",
              dateLabel: "Date",
            })}
          </div>

          <div ref={labsRef} className={sectionClass("labs")} data-section="labs">
            <div className={styles.cardHeader}>
              <div>
                <h2>Labs</h2>
                <p>Numeric values only. Add a date when possible for time-window rules.</p>
              </div>
            </div>

            {fieldErrors.labs ? (
              <Toast
                tone="warning"
                title="Lab value needed"
                description={fieldErrors.labs}
              />
            ) : null}
            {renderLabRows()}
          </div>

          <div ref={otherRef} className={sectionClass("other")} data-section="other">
            <div className={styles.cardHeader}>
              <div>
                <h2>Other notes</h2>
                <p>Optional clinical notes relevant to matching (synthetic only).</p>
              </div>
            </div>

            <Field
              label="Notes"
              htmlFor="patient-other"
              hint="Comma or newline separated. Keep it short and synthetic."
            >
              <textarea
                id="patient-other"
                className={`ui-input ${styles.textarea}`}
                value={otherText}
                onChange={(event) => setOtherText(event.target.value)}
                placeholder="smoking status: never"
              />
            </Field>

            <div className={styles.actions}>
              <Button
                tone="primary"
                size="md"
                onClick={onSave}
                disabled={saving || sessionStatus === "unavailable" || patientLoading}
                iconLeft={<PencilLine size={18} aria-hidden="true" />}
                iconRight={<Save size={18} aria-hidden="true" />}
              >
                {saving ? "Saving..." : "Save changes"}
              </Button>
              <Link
                href={patientId ? `/patients/${encodeURIComponent(patientId)}` : "/patients"}
                className="ui-button ui-button--ghost ui-button--md"
              >
                Cancel
              </Link>
            </div>
          </div>
        </div>

        <div className={styles.aside}>
          <Card className={styles.card}>
            <h3 className={styles.asideTitle}>Preview</h3>
            {patientLoading ? (
              <div style={{ marginTop: 12 }}>
                <Skeleton width="long" />
                <div style={{ marginTop: 10 }}>
                  <Skeleton width="medium" />
                </div>
              </div>
            ) : !patient ? (
              <EmptyState
                title="Patient unavailable"
                description="This profile may not exist in your session."
              />
            ) : (
              <>
                <div className={styles.pills}>
                  <Pill tone="neutral">
                    Age {Number.isFinite(Number(age)) ? Math.trunc(Number(age)) : "?"}
                  </Pill>
                  <Pill tone="neutral">{sex.trim() || "sex?"}</Pill>
                  <Pill tone="brand">{previewConditions.length} conditions</Pill>
                  <Pill tone="info">{previewLabs.length} labs</Pill>
                </div>

                {previewConditions.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <strong>Conditions</strong>
                    <ul className={styles.previewList}>
                      {previewConditions.slice(0, 6).map((entry) => (
                        <li key={entry}>{entry}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {previewHistory.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <strong>History</strong>
                    <ul className={styles.previewList}>
                      {previewHistory.slice(0, 4).map((entry, idx) => (
                        <li key={idx}>
                          {typeof entry === "string" ? entry : entry?.name || ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div style={{ marginTop: 12, color: "var(--muted)", fontSize: 13 }}>
                  Patient data is stored in the preview database and scoped to your current
                  browser token. Do not enter real PHI.
                </div>
              </>
            )}
          </Card>
        </div>
      </div>
    </Shell>
  );
}
