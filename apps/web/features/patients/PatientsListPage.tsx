import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarClock, ChevronLeft, ChevronRight, Plus, UserRound } from "lucide-react";

import { Shell } from "../../components/layout/Shell";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { Pill } from "../../components/ui/Pill";
import { Select } from "../../components/ui/Select";
import { Skeleton } from "../../components/ui/Skeleton";
import { Toast } from "../../components/ui/Toast";
import { ApiError } from "../../lib/http/client";
import { ensureSession, withSessionRetry } from "../../lib/session/session";

import { listPatients } from "./api";
import type { Patient } from "./types";
import styles from "./PatientsListPage.module.css";

const formatDate = (value?: string | null) => {
  if (!value) {
    return null;
  }
  return value.length >= 10 ? value.slice(0, 10) : value;
};

const patientPrimaryCondition = (patient: Patient): string => {
  const conditions = patient.profile_json?.conditions;
  if (!Array.isArray(conditions) || conditions.length === 0) {
    return "Patient profile";
  }
  return conditions[0] || "Patient profile";
};

const patientSummary = (patient: Patient): string => {
  const demo = patient.profile_json?.demographics;
  const age = typeof demo?.age === "number" ? String(Math.trunc(demo.age)) : "";
  const sex = typeof demo?.sex === "string" ? demo.sex.trim() : "";
  const parts = [sex, age ? `${age}y` : ""].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Demographics not provided";
};

export default function PatientsListPage() {
  const [sessionStatus, setSessionStatus] = useState<
    "loading" | "ready" | "unavailable"
  >("loading");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const totalPages = useMemo(() => {
    if (total <= 0) {
      return 1;
    }
    return Math.max(1, Math.ceil(total / pageSize));
  }, [pageSize, total]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);

      const session = await ensureSession({
        envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
        allowPreviewIssue: true,
      });
      if (cancelled) {
        return;
      }
      setSessionStatus(session.status);
      if (!session.token) {
        setPatients([]);
        setTotal(0);
        setLoading(false);
        return;
      }

      try {
        const data = await withSessionRetry(
          (token) => listPatients({ token, page, pageSize }),
          {
            envToken: process.env.NEXT_PUBLIC_DEV_JWT ?? "",
            allowPreviewIssue: true,
          }
        );
        if (cancelled) {
          return;
        }
        setPatients(Array.isArray(data.patients) ? data.patients : []);
        setTotal(Number.isFinite(data.total) ? data.total : 0);
      } catch (err) {
        if (cancelled) {
          return;
        }
        if (err instanceof ApiError) {
          setError(err.message);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Failed to load patients");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [page, pageSize]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const rangeLabel = useMemo(() => {
    if (total === 0) {
      return "0 patients";
    }
    const start = (page - 1) * pageSize + 1;
    const end = Math.min(total, page * pageSize);
    return `${start}-${end} of ${total}`;
  }, [page, pageSize, total]);

  return (
    <Shell
      className={styles.page}
      kicker="Patients hub"
      title="Patients"
      subtitle="Create and manage patient profiles. Run matching and revisit past results from a single place."
      actions={
        <Link
          href="/patients/new"
          className="ui-button ui-button--primary ui-button--md"
        >
          <span className="ui-button__icon" aria-hidden="true">
            <Plus size={18} />
          </span>
          <span className="ui-button__label">New patient</span>
        </Link>
      }
    >
      {sessionStatus === "unavailable" ? (
        <Toast
          tone="warning"
          title="Session unavailable"
          description="This preview could not start an authenticated session. Try refreshing the page."
        />
      ) : null}
      {error ? (
        <Toast tone="danger" title="Could not load patients" description={error} />
      ) : null}

      <div className={styles.layout}>
        <Card className={styles.listCard}>
          <div className={styles.listHeader}>
            <div className={styles.listTitle}>
              <h2>Saved patient profiles</h2>
              <p>Profiles are scoped to this browser session (preview).</p>
            </div>
            <div>
              <Select
                aria-label="Page size"
                value={String(pageSize)}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setPageSize(Number.isFinite(next) ? next : 20);
                  setPage(1);
                }}
              >
                <option value="10">10 / page</option>
                <option value="20">20 / page</option>
                <option value="50">50 / page</option>
              </Select>
            </div>
          </div>

          <div className={styles.listBody}>
            {loading ? (
              <div>
                <Skeleton width="long" />
                <div style={{ marginTop: 10 }}>
                  <Skeleton width="medium" />
                </div>
                <div style={{ marginTop: 18 }}>
                  {Array.from({ length: 6 }).map((_, idx) => (
                    <div key={idx} style={{ padding: "12px 0" }}>
                      <Skeleton width="long" />
                      <div style={{ marginTop: 10 }}>
                        <Skeleton width="medium" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : patients.length === 0 ? (
              <EmptyState
                icon={<UserRound size={28} aria-hidden="true" />}
                title="No patients yet"
                description="Create your first patient profile to start matching."
                actions={
                  <Link
                    href="/patients/new"
                    className="ui-button ui-button--primary ui-button--md"
                  >
                    <span className="ui-button__label">Create a patient</span>
                    <span className="ui-button__icon" aria-hidden="true">
                      <ChevronRight size={18} />
                    </span>
                  </Link>
                }
              />
            ) : (
              <>
                {patients.map((patient) => {
                  const primary = patientPrimaryCondition(patient);
                  const summary = patientSummary(patient);
                  const created = formatDate(patient.created_at);
                  const conditionCount = Array.isArray(patient.profile_json?.conditions)
                    ? patient.profile_json.conditions.length
                    : 0;
                  return (
                    <div key={patient.id} className={styles.patientRow}>
                      <div>
                        <div className={styles.patientHeading}>
                          <Link
                            href={`/patients/${patient.id}`}
                            className={styles.patientName}
                          >
                            {primary}
                          </Link>
                          <Pill tone="neutral">{summary}</Pill>
                        </div>
                        <div className={styles.patientMeta}>
                          <span className={styles.metaItem}>
                            <span aria-hidden="true">Conditions:</span>
                            <span>{conditionCount || 0}</span>
                          </span>
                          {created ? (
                            <span className={styles.metaItem}>
                              <CalendarClock size={14} aria-hidden="true" />
                              <span>Created {created}</span>
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <div className={styles.rowActions}>
                        <Link
                          href={`/patients/${patient.id}`}
                          className="ui-button ui-button--secondary ui-button--sm"
                        >
                          View
                        </Link>
                      </div>
                    </div>
                  );
                })}

                <div className={styles.pagination}>
                  <div className={styles.metaItem}>{rangeLabel}</div>
                  <div className={styles.paginationControls}>
                    <Button
                      tone="secondary"
                      size="sm"
                      onClick={() => setPage((value) => Math.max(1, value - 1))}
                      disabled={page <= 1}
                      iconLeft={<ChevronLeft size={16} aria-hidden="true" />}
                    >
                      Prev
                    </Button>
                    <Button
                      tone="secondary"
                      size="sm"
                      onClick={() =>
                        setPage((value) => Math.min(totalPages, value + 1))
                      }
                      disabled={page >= totalPages}
                      iconRight={<ChevronRight size={16} aria-hidden="true" />}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </Card>

        <div className={styles.aside}>
          <Card className={styles.asideCard}>
            <h3 className={styles.asideTitle}>Quick start</h3>
            <div className={styles.asideBody}>
              <div>
                Create a patient once, then run multiple matches with different
                filters (status/phase/location) without re-entering data.
              </div>
              <div className={styles.asideLinks}>
                <Link href="/patients/new" className="ui-button ui-button--primary ui-button--md">
                  New patient
                </Link>
                <Link href="/match" className="ui-button ui-button--ghost ui-button--md">
                  One-off match
                </Link>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </Shell>
  );
}
