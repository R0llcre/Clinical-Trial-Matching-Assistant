export type PatientDemographics = {
  age: number;
  sex: string;
};

export type PatientProfileJson = {
  demographics: PatientDemographics;
  conditions?: string[];
  history?: string[];
  medications?: string[];
  procedures?: string[];
  [key: string]: unknown;
};

export type Patient = {
  id: string;
  source: string;
  profile_json: PatientProfileJson;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PatientsListData = {
  patients: Patient[];
  total: number;
  page: number;
  page_size: number;
};

export type MatchQueryJson = {
  filters?: Record<string, string>;
  top_k?: number;
  [key: string]: unknown;
};

export type MatchListItem = {
  id: string;
  patient_profile_id: string;
  query_json: MatchQueryJson;
  created_at?: string | null;
};

export type MatchesListData = {
  matches: MatchListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type CreateMatchData = {
  match_id: string;
  results?: unknown[];
};

