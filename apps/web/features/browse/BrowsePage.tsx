import Link from "next/link";
import type { GetServerSideProps } from "next";
import { useRouter } from "next/router";
import type { FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Building2,
  Filter,
  MapPin,
  RefreshCcw,
  Search,
  XCircle,
} from "lucide-react";

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
import styles from "./BrowsePage.module.css";

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

const buildQueryKey = (input: {
  condition: string;
  status: string;
  phase: string;
  country: string;
  state: string;
  city: string;
  page: number;
  pageSize: number;
}) => {
  return [
    input.condition.trim(),
    input.status.trim(),
    input.phase.trim(),
    input.country.trim(),
    input.state.trim(),
    input.city.trim(),
    String(input.page),
    String(input.pageSize),
  ].join("|");
};

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

const statusTone = (
  value?: string | null
): "neutral" | "brand" | "success" | "warning" | "danger" | "info" => {
  if (!value) {
    return "neutral";
  }
  if (value === "RECRUITING") {
    return "success";
  }
  if (value === "NOT_YET_RECRUITING") {
    return "info";
  }
  if (value === "ACTIVE_NOT_RECRUITING") {
    return "brand";
  }
  if (value === "COMPLETED") {
    return "neutral";
  }
  return "neutral";
};

const phaseLabel = (value?: string | null) => {
  if (!value) {
    return null;
  }
  if (value === "EARLY_PHASE1") {
    return "Early Phase 1";
  }
  if (value === "PHASE1") {
    return "Phase 1";
  }
  if (value === "PHASE2") {
    return "Phase 2";
  }
  if (value === "PHASE3") {
    return "Phase 3";
  }
  if (value === "PHASE4") {
    return "Phase 4";
  }
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (match) => match.toUpperCase());
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
  initialCountry: string;
  initialState: string;
  initialCity: string;
};

export const getServerSideProps: GetServerSideProps<HomeProps> = async (ctx) => {
  const condition =
    typeof ctx.query.condition === "string" ? ctx.query.condition : "";
  const status = typeof ctx.query.status === "string" ? ctx.query.status : "";
  const phase = typeof ctx.query.phase === "string" ? ctx.query.phase : "";
  const country =
    typeof ctx.query.country === "string" ? ctx.query.country : "";
  const state =
    typeof ctx.query.state === "string" ? ctx.query.state : "";
  const city =
    typeof ctx.query.city === "string" ? ctx.query.city : "";
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
  if (country.trim()) {
    params.set("country", country.trim());
  }
  if (state.trim()) {
    params.set("state", state.trim());
  }
  if (city.trim()) {
    params.set("city", city.trim());
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
          initialCountry: country,
          initialState: state,
          initialCity: city,
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
        initialCountry: country,
        initialState: state,
        initialCity: city,
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
        initialCountry: country,
        initialState: state,
        initialCity: city,
      },
    };
  }
};

export default function Home(props: HomeProps) {
  const router = useRouter();
  const [condition, setCondition] = useState(props.initialCondition);
  const [status, setStatus] = useState(props.initialStatus);
  const [phase, setPhase] = useState(props.initialPhase);
  const [country, setCountry] = useState(props.initialCountry);
  const [regionState, setRegionState] = useState(props.initialState);
  const [city, setCity] = useState(props.initialCity);
  const [trials, setTrials] = useState<TrialSummary[]>(props.initialTrials);
  const [page, setPage] = useState(props.initialPage);
  const [pageSize, setPageSize] = useState(props.initialPageSize);
  const [total, setTotal] = useState(props.initialTotal);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastFetchedQueryKeyRef = useRef(
    buildQueryKey({
      condition: props.initialCondition,
      status: props.initialStatus,
      phase: props.initialPhase,
      country: props.initialCountry,
      state: props.initialState,
      city: props.initialCity,
      page: props.initialPage,
      pageSize: props.initialPageSize,
    })
  );

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
    countryValue: string;
    stateValue: string;
    cityValue: string;
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
    const trimmedCountry = input.countryValue.trim();
    if (trimmedCountry) {
      query.country = trimmedCountry;
    }
    const trimmedState = input.stateValue.trim();
    if (trimmedState) {
      query.state = trimmedState;
    }
    const trimmedCity = input.cityValue.trim();
    if (trimmedCity) {
      query.city = trimmedCity;
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
    countryValue: string;
    stateValue: string;
    cityValue: string;
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
    if (input.countryValue.trim()) {
      params.set("country", input.countryValue.trim());
    }
    if (input.stateValue.trim()) {
      params.set("state", input.stateValue.trim());
    }
    if (input.cityValue.trim()) {
      params.set("city", input.cityValue.trim());
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
      lastFetchedQueryKeyRef.current = buildQueryKey({
        condition: input.conditionValue,
        status: input.statusValue,
        phase: input.phaseValue,
        country: input.countryValue,
        state: input.stateValue,
        city: input.cityValue,
        page: payload.data?.page ?? input.pageValue,
        pageSize: payload.data?.page_size ?? input.pageSizeValue,
      });
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
      countryValue: country,
      stateValue: regionState,
      cityValue: city,
      pageValue: 1,
      pageSizeValue: pageSize,
    });
    void router.push({ pathname: "/", query }, undefined, { shallow: true });
  };

  const clearFilters = () => {
    setCondition("");
    setStatus("");
    setPhase("");
    setCountry("");
    setRegionState("");
    setCity("");
    const query = buildQuery({
      conditionValue: "",
      statusValue: "",
      phaseValue: "",
      countryValue: "",
      stateValue: "",
      cityValue: "",
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

  const suggestedLocations = useMemo(() => {
    const counts = new Map<string, number>();
    for (const trial of trials) {
      for (const rawLocation of trial.locations ?? []) {
        const value = rawLocation.trim();
        if (!value) {
          continue;
        }
        counts.set(value, (counts.get(value) ?? 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 8)
      .map(([value]) => value);
  }, [trials]);

  const suggestedCountries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const location of suggestedLocations) {
      const parts = location
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const countryValue = parts.at(-1);
      if (!countryValue) {
        continue;
      }
      counts.set(countryValue, (counts.get(countryValue) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 6)
      .map(([value]) => value);
  }, [suggestedLocations]);

  const hasAnyFilter = Boolean(
    condition.trim() ||
      status ||
      phase ||
      country.trim() ||
      regionState.trim() ||
      city.trim()
  );

  const activeFilters = useMemo(() => {
    return [
      condition.trim() ? { key: "Condition", value: condition.trim() } : null,
      status ? { key: "Status", value: statusLabel(status) ?? status } : null,
      phase ? { key: "Phase", value: phaseLabel(phase) ?? phase } : null,
      country.trim() ? { key: "Country", value: country.trim() } : null,
      regionState.trim() ? { key: "State", value: regionState.trim() } : null,
      city.trim() ? { key: "City", value: city.trim() } : null,
    ].filter(Boolean) as Array<{ key: string; value: string }>;
  }, [condition, status, phase, country, regionState, city]);

  const visibleStart = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const visibleEnd = total > 0 ? Math.min(total, page * pageSize) : 0;

  const SAMPLE_QUERIES = [
    "Breast cancer",
    "Melanoma",
    "Asthma",
    "Diabetes",
    "Long COVID",
    "Leukemia",
  ];

  useEffect(() => {
    // When Next.js re-hydrates new SSR props (non-shallow navigation), prefer them.
    abortRef.current?.abort();
    setLoading(false);
    setError(null);
    setCondition(props.initialCondition);
    setStatus(props.initialStatus);
    setPhase(props.initialPhase);
    setCountry(props.initialCountry);
    setRegionState(props.initialState);
    setCity(props.initialCity);
    setTrials(props.initialTrials);
    setTotal(props.initialTotal);
    setPage(props.initialPage);
    setPageSize(props.initialPageSize);
    lastFetchedQueryKeyRef.current = buildQueryKey({
      condition: props.initialCondition,
      status: props.initialStatus,
      phase: props.initialPhase,
      country: props.initialCountry,
      state: props.initialState,
      city: props.initialCity,
      page: props.initialPage,
      pageSize: props.initialPageSize,
    });
  }, [
    props.initialCondition,
    props.initialStatus,
    props.initialPhase,
    props.initialCountry,
    props.initialState,
    props.initialCity,
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
    const nextCountry =
      typeof router.query.country === "string" ? router.query.country : "";
    const nextState =
      typeof router.query.state === "string" ? router.query.state : "";
    const nextCity =
      typeof router.query.city === "string" ? router.query.city : "";
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
    const nextQueryKey = buildQueryKey({
      condition: nextCondition,
      status: nextStatus,
      phase: nextPhase,
      country: nextCountry,
      state: nextState,
      city: nextCity,
      page: safePage,
      pageSize: safePageSize,
    });
    const shouldFetch = nextQueryKey !== lastFetchedQueryKeyRef.current;

    setCondition(nextCondition);
    setStatus(nextStatus);
    setPhase(nextPhase);
    setCountry(nextCountry);
    setRegionState(nextState);
    setCity(nextCity);
    setPage(safePage);
    setPageSize(safePageSize);

    if (!shouldFetch) {
      return;
    }

    void fetchTrials({
      conditionValue: nextCondition,
      statusValue: nextStatus,
      phaseValue: nextPhase,
      countryValue: nextCountry,
      stateValue: nextState,
      cityValue: nextCity,
      pageValue: safePage,
      pageSizeValue: safePageSize,
    });
  }, [
    router.isReady,
    router.asPath,
    props.initialCondition,
    props.initialStatus,
    props.initialPhase,
    props.initialCountry,
    props.initialState,
    props.initialCity,
    props.initialPage,
    props.initialPageSize,
  ]);

  return (
    <Shell
      className={styles.page}
      kicker="Clinical Trial Explorer"
      title="Browse trials"
      subtitle={
        <>
          Search synced <strong>ClinicalTrials.gov</strong> listings, review eligibility,
          and hand results to a clinician. This preview surfaces information only, not
          medical advice.
        </>
      }
      actions={
        <>
          <Link
            href="/match"
            className="ui-button ui-button--primary ui-button--md"
          >
            Start matching
            <span className="ui-button__icon" aria-hidden="true">
              <ArrowRight size={18} />
            </span>
          </Link>
          <Link
            href="/"
            className="ui-button ui-button--ghost ui-button--md"
            onClick={(event) => {
              if (!hasAnyFilter) {
                event.preventDefault();
              }
            }}
          >
            Browse
          </Link>
        </>
      }
    >
      <div className="browse-layout">
        <aside className="browse-rail">
          <Card className="browse-rail__card">
            <div className="browse-rail__title">
              <Filter size={18} aria-hidden="true" />
              <h2 className="browse-rail__titleText">Filters</h2>
            </div>

            <form className="browse-rail__form" onSubmit={handleSubmit}>
              <div className="browse-rail__group">
                <div className="browse-rail__groupHeader">
                  <Search size={16} aria-hidden="true" />
                  <h3 className="browse-rail__groupTitle">Condition</h3>
                </div>
                <Field
                  label="Condition"
                  htmlFor="condition"
                  hint="Matches title and listed conditions."
                >
                  <Input
                    id="condition"
                    name="condition"
                    placeholder="e.g. breast cancer"
                    value={condition}
                    onChange={(event) => setCondition(event.target.value)}
                  />
                </Field>
                <div className="browse-rail__chips">
                  {(suggestedConditions.length > 0
                    ? suggestedConditions
                    : SAMPLE_QUERIES
                  ).map((value) => (
                    <button
                      key={value}
                      type="button"
                      className="browse-chip ui-pill ui-pill--neutral"
                      onClick={() => {
                        setCondition(value);
                        const query = buildQuery({
                          conditionValue: value,
                          statusValue: status,
                          phaseValue: phase,
                          countryValue: country,
                          stateValue: regionState,
                          cityValue: city,
                          pageValue: 1,
                          pageSizeValue: pageSize,
                        });
                        void router.push({ pathname: "/", query }, undefined, {
                          shallow: true,
                        });
                      }}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              <div className="browse-rail__group">
                <div className="browse-rail__groupHeader">
                  <Building2 size={16} aria-hidden="true" />
                  <h3 className="browse-rail__groupTitle">Status & phase</h3>
                </div>
                <Field label="Recruitment status" htmlFor="status">
                  <Select
                    id="status"
                    value={status}
                    onChange={(event) => {
                      const value = event.target.value;
                      setStatus(value);
                      const query = buildQuery({
                        conditionValue: condition,
                        statusValue: value,
                        phaseValue: phase,
                        countryValue: country,
                        stateValue: regionState,
                        cityValue: city,
                        pageValue: 1,
                        pageSizeValue: pageSize,
                      });
                      void router.push({ pathname: "/", query }, undefined, {
                        shallow: true,
                      });
                    }}
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
                    onChange={(event) => {
                      const value = event.target.value;
                      setPhase(value);
                      const query = buildQuery({
                        conditionValue: condition,
                        statusValue: status,
                        phaseValue: value,
                        countryValue: country,
                        stateValue: regionState,
                        cityValue: city,
                        pageValue: 1,
                        pageSizeValue: pageSize,
                      });
                      void router.push({ pathname: "/", query }, undefined, {
                        shallow: true,
                      });
                    }}
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

              <div className="browse-rail__group">
                <div className="browse-rail__groupHeader">
                  <MapPin size={16} aria-hidden="true" />
                  <h3 className="browse-rail__groupTitle">Location</h3>
                </div>
                <Field label="Country (exact match)" htmlFor="country">
                  <Input
                    id="country"
                    name="country"
                    placeholder="United States"
                    value={country}
                    onChange={(event) => setCountry(event.target.value)}
                  />
                </Field>
                {suggestedCountries.length > 0 ? (
                  <div className="browse-rail__chips browse-rail__chips--tight">
                    {suggestedCountries.map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="browse-chip ui-pill ui-pill--info"
                        onClick={() => {
                          setCountry(value);
                          const query = buildQuery({
                            conditionValue: condition,
                            statusValue: status,
                            phaseValue: phase,
                            countryValue: value,
                            stateValue: regionState,
                            cityValue: city,
                            pageValue: 1,
                            pageSizeValue: pageSize,
                          });
                          void router.push({ pathname: "/", query }, undefined, {
                            shallow: true,
                          });
                        }}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="browse-rail__row">
                  <Field label="State" htmlFor="state">
                    <Input
                      id="state"
                      name="state"
                      placeholder="NY"
                      value={regionState}
                      onChange={(event) => setRegionState(event.target.value)}
                    />
                  </Field>
                  <Field label="City" htmlFor="city">
                    <Input
                      id="city"
                      name="city"
                      placeholder="New York"
                      value={city}
                      onChange={(event) => setCity(event.target.value)}
                    />
                  </Field>
                </div>
              </div>

              <div className="browse-rail__actions">
                <Button type="submit" tone="primary" disabled={loading}>
                  {loading ? "Searching..." : "Search"}
                </Button>
                {hasAnyFilter ? (
                  <Button
                    type="button"
                    tone="ghost"
                    disabled={loading}
                    iconLeft={<XCircle size={18} />}
                    onClick={clearFilters}
                  >
                    Clear
                  </Button>
                ) : null}
              </div>
            </form>
          </Card>

          <Card tone="subtle" className="browse-rail__card">
            <div className="browse-dataset">
              <div className="browse-dataset__header">Dataset</div>
              <div className="browse-dataset__grid">
                <div className="browse-dataset__stat">
                  <div className="browse-dataset__value">{total || "—"}</div>
                  <div className="browse-dataset__label">trials indexed</div>
                </div>
                <div className="browse-dataset__stat">
                  <div className="browse-dataset__value">{lastSyncedDate || "—"}</div>
                  <div className="browse-dataset__label">latest sync</div>
                </div>
              </div>
              <div className="browse-dataset__hint">
                Filters match exact location fields, so start broad then narrow.
              </div>
            </div>
          </Card>
        </aside>

        <section className={`browse-results ${styles.resultsWorkspace}`}>
          <div className="browse-results__header">
            <div className="browse-results__meta">
              <div className="browse-results__title">Results</div>
              <div className="browse-results__subtitle">
                {total > 0
                  ? `Showing ${visibleStart}–${visibleEnd} of ${total}`
                  : "No trials in the current view."}
              </div>
            </div>

            <div className="browse-results__controls">
              <div className="browse-control">
                <span className="browse-control__label">Page size</span>
                <Select
                  value={String(pageSize)}
                  onChange={(event) => {
                    const nextSize = Number(event.target.value);
                    const query = buildQuery({
                      conditionValue: condition,
                      statusValue: status,
                      phaseValue: phase,
                      countryValue: country,
                      stateValue: regionState,
                      cityValue: city,
                      pageValue: 1,
                      pageSizeValue: nextSize,
                    });
                    void router.push({ pathname: "/", query }, undefined, {
                      shallow: true,
                    });
                  }}
                  disabled={loading}
                >
                  <option value="20">20</option>
                  <option value="50">50</option>
                </Select>
              </div>
              <button
                type="button"
                className="ui-button ui-button--ghost ui-button--sm browse-refresh"
                disabled={loading}
                onClick={() => {
                  void fetchTrials({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    countryValue: country,
                    stateValue: regionState,
                    cityValue: city,
                    pageValue: page,
                    pageSizeValue: pageSize,
                  });
                }}
              >
                <span className="ui-button__icon" aria-hidden="true">
                  <RefreshCcw size={18} />
                </span>
                Refresh
              </button>
            </div>
          </div>

          {activeFilters.length > 0 ? (
            <div className="browse-results__activeFilters">
              <div className="browse-results__activeFiltersLabel">Active filters</div>
              <div className="browse-results__activeFiltersPills">
                {activeFilters.map((item) => (
                  <Pill key={`${item.key}-${item.value}`} tone="brand">
                    {item.key}: {item.value}
                  </Pill>
                ))}
                <button
                  type="button"
                  className="ui-button ui-button--ghost ui-button--sm"
                  onClick={clearFilters}
                  disabled={loading}
                >
                  Clear all
                </button>
              </div>
            </div>
          ) : null}

          {error ? (
            <Toast
              tone="danger"
              title="Search failed"
              description={error}
              className="browse-toast"
            />
          ) : null}

          <div className="browse-list">
            {loading && trials.length === 0 ? (
              <>
                {Array.from({ length: 6 }).map((_, index) => (
                  <Card key={`skeleton-${index}`} className="trial-card-v3">
                    <div className="trial-card-v3__header">
                      <div className="trial-card-v3__pills">
                        <Skeleton width="short" />
                        <Skeleton width="medium" />
                      </div>
                      <Skeleton width="short" />
                    </div>
                    <div className="trial-card-v3__title">
                      <Skeleton width="long" />
                    </div>
                    <Skeleton width="long" />
                    <div className="trial-card-v3__chips">
                      <Skeleton width="short" />
                      <Skeleton width="short" />
                      <Skeleton width="short" />
                    </div>
                  </Card>
                ))}
              </>
            ) : null}

            {!loading && trials.length === 0 ? (
              <EmptyState
                title="No trials found"
                description="Try a broader condition, loosen filters (especially location), or run a patient match instead."
                icon={<Search size={22} />}
                actions={
                  <>
                    <button
                      type="button"
                      className="ui-button ui-button--primary ui-button--md"
                      onClick={clearFilters}
                    >
                      Clear filters
                    </button>
                    <Link
                      href="/match"
                      className="ui-button ui-button--secondary ui-button--md"
                    >
                      Go to matching
                    </Link>
                  </>
                }
              />
            ) : null}

            {trials.map((trial) => {
              const statusText = statusLabel(trial.status);
              const phaseText = phaseLabel(trial.phase);
              const conditionsShown = (trial.conditions ?? []).slice(0, 3);
              const conditionsRemaining =
                (trial.conditions?.length ?? 0) - conditionsShown.length;
              const locationsShown = (trial.locations ?? []).slice(0, 2);
              const locationsRemaining =
                (trial.locations?.length ?? 0) - locationsShown.length;

              return (
                <Card className="trial-card-v3" key={trial.nct_id}>
                  <div className="trial-card-v3__header">
                    <div className="trial-card-v3__pills">
                      <Pill tone="warning">{trial.nct_id}</Pill>
                      {statusText ? (
                        <Pill tone={statusTone(trial.status)}>{statusText}</Pill>
                      ) : null}
                      {phaseText ? <Pill tone="neutral">{phaseText}</Pill> : null}
                    </div>
                    {trial.fetched_at ? (
                      <div className="trial-card-v3__updated">
                        Synced {formatFetchedDate(trial.fetched_at)}
                      </div>
                    ) : null}
                  </div>

                  <Link
                    href={`/trials/${trial.nct_id}`}
                    className="trial-card-v3__link"
                  >
                    {trial.title}
                  </Link>

                  <div className="trial-card-v3__locations">
                    <MapPin size={16} aria-hidden="true" />
                    <span className="trial-card-v3__locationsText">
                      {locationsShown.length > 0
                        ? locationsShown.join(" · ")
                        : "Location data pending"}
                      {locationsRemaining > 0 ? ` · +${locationsRemaining} more` : ""}
                    </span>
                  </div>

                  <div className="trial-card-v3__chips">
                    {conditionsShown.map((value) => (
                      <Pill key={`${trial.nct_id}-${value}`} tone="neutral">
                        {value}
                      </Pill>
                    ))}
                    {conditionsRemaining > 0 ? (
                      <Pill tone="info">+{conditionsRemaining} conditions</Pill>
                    ) : null}
                  </div>

                  <div className="trial-card-v3__actions">
                    <Link
                      href={`/trials/${trial.nct_id}`}
                      className="ui-button ui-button--ghost ui-button--sm"
                    >
                      View details
                    </Link>
                    <Link
                      href={{
                        pathname: "/match",
                        query: trial.conditions?.[0]
                          ? { condition: trial.conditions[0] }
                          : undefined,
                      }}
                      className="ui-button ui-button--secondary ui-button--sm"
                    >
                      Use for match
                      <span className="ui-button__icon" aria-hidden="true">
                        <ArrowRight size={18} />
                      </span>
                    </Link>
                  </div>
                </Card>
              );
            })}
          </div>

          {trials.length > 0 ? (
            <div className="browse-pagination">
              <button
                className="ui-button ui-button--secondary ui-button--md"
                onClick={() => {
                  const query = buildQuery({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    countryValue: country,
                    stateValue: regionState,
                    cityValue: city,
                    pageValue: Math.max(1, page - 1),
                    pageSizeValue: pageSize,
                  });
                  void router.push({ pathname: "/", query }, undefined, {
                    shallow: true,
                  });
                }}
                disabled={loading || page <= 1}
              >
                Previous
              </button>
              <div className="browse-pagination__meta">
                Page <strong>{page}</strong> of <strong>{totalPages}</strong>
              </div>
              <button
                className="ui-button ui-button--secondary ui-button--md"
                onClick={() => {
                  const query = buildQuery({
                    conditionValue: condition,
                    statusValue: status,
                    phaseValue: phase,
                    countryValue: country,
                    stateValue: regionState,
                    cityValue: city,
                    pageValue: Math.min(totalPages, page + 1),
                    pageSizeValue: pageSize,
                  });
                  void router.push({ pathname: "/", query }, undefined, {
                    shallow: true,
                  });
                }}
                disabled={loading || page >= totalPages}
              >
                Next
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </Shell>
  );
}
