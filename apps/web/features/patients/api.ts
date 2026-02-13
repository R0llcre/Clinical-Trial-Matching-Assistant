import { fetchOk } from "../../lib/http/client";

import type {
  CreateMatchData,
  MatchesListData,
  Patient,
  PatientProfileJson,
  PatientsListData,
} from "./types";

const authHeaders = (token: string) => ({
  Authorization: `Bearer ${token}`,
});

export async function listPatients(input: {
  token: string;
  page: number;
  pageSize: number;
}): Promise<PatientsListData> {
  const params = new URLSearchParams();
  params.set("page", String(input.page));
  params.set("page_size", String(input.pageSize));

  return fetchOk<PatientsListData>(`/api/patients?${params.toString()}`, {
    headers: authHeaders(input.token),
  });
}

export async function getPatient(input: {
  token: string;
  patientId: string;
}): Promise<Patient> {
  const id = encodeURIComponent(input.patientId);
  return fetchOk<Patient>(`/api/patients/${id}`, {
    headers: authHeaders(input.token),
  });
}

export async function createPatient(input: {
  token: string;
  profileJson: PatientProfileJson;
  source?: string;
}): Promise<Patient> {
  return fetchOk<Patient>("/api/patients", {
    method: "POST",
    headers: authHeaders(input.token),
    body: {
      profile_json: input.profileJson,
      source: input.source ?? "manual",
    },
  });
}

export async function listMatches(input: {
  token: string;
  patientProfileId?: string;
  page: number;
  pageSize: number;
}): Promise<MatchesListData> {
  const params = new URLSearchParams();
  params.set("page", String(input.page));
  params.set("page_size", String(input.pageSize));
  if (input.patientProfileId) {
    params.set("patient_profile_id", input.patientProfileId);
  }
  return fetchOk<MatchesListData>(`/api/matches?${params.toString()}`, {
    headers: authHeaders(input.token),
  });
}

export async function createMatch(input: {
  token: string;
  patientProfileId: string;
  topK: number;
  filters: Record<string, string>;
}): Promise<CreateMatchData> {
  return fetchOk<CreateMatchData>("/api/match", {
    method: "POST",
    headers: authHeaders(input.token),
    body: {
      patient_profile_id: input.patientProfileId,
      top_k: input.topK,
      filters: input.filters,
    },
  });
}

