export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type ApiEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "API_ERROR") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type FetchJsonOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export async function fetchJson<T>(
  path: string,
  options: FetchJsonOptions = {}
): Promise<{ response: Response; payload: ApiEnvelope<T> | null }> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const { method = "GET", body, headers, signal } = options;

  const response = await fetch(url, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers ?? {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  let payload: ApiEnvelope<T> | null = null;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    payload = null;
  }

  return { response, payload };
}

export async function fetchOk<T>(
  path: string,
  options: FetchJsonOptions = {}
): Promise<T> {
  const { response, payload } = await fetchJson<T>(path, options);
  if (!response.ok || !payload?.ok || payload.data === undefined) {
    throw new ApiError(
      payload?.error?.message ?? `Request failed (${response.status})`,
      response.status,
      payload?.error?.code ?? "API_ERROR"
    );
  }
  return payload.data;
}
