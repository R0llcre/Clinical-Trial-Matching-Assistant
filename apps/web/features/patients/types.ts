export type PatientDemographics = {
  age: number;
  sex: string;
};

export type PatientNamedDateEntry = {
  name: string;
  date?: string;
};

export type PatientTimelineEntry = string | PatientNamedDateEntry;

export type PatientLabEntry = {
  name: string;
  value: number;
  date?: string;
};

export type PatientProfileJson = {
  demographics: PatientDemographics;
  conditions?: string[];
  history?: PatientTimelineEntry[];
  medications?: PatientTimelineEntry[];
  procedures?: PatientTimelineEntry[];
  labs?: PatientLabEntry[];
  other?: string[];
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
