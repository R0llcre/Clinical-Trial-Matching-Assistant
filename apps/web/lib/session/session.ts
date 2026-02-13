import { API_BASE, fetchJson } from "../http/client";

export const SESSION_KEY = "ctmatch.jwt";
export const PREVIEW_SUB_KEY = "ctmatch.preview_sub";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isUuid(value: string): boolean {
  return UUID_RE.test(value.trim());
}

function fallbackUuidV4(): string {
  const bytes = new Uint8Array(16);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Math.floor(Math.random() * 256);
  }
  // RFC 4122 v4
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    ""
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(
    12,
    16
  )}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function getOrCreatePreviewSub(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const existing = (window.localStorage.getItem(PREVIEW_SUB_KEY) ?? "").trim();
  if (existing && isUuid(existing)) {
    return existing;
  }

  const generated =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : fallbackUuidV4();

  window.localStorage.setItem(PREVIEW_SUB_KEY, generated);
  return generated;
}

function jwtSubject(token: string): string {
  if (typeof window === "undefined") {
    return "";
  }
  const parts = token.split(".");
  if (parts.length < 2) {
    return "";
  }

  try {
    const base64Url = parts[1] ?? "";
    const base64 = base64Url
      .replaceAll("-", "+")
      .replaceAll("_", "/")
      .padEnd(Math.ceil(base64Url.length / 4) * 4, "=");
    const json = window.atob(base64);
    const payload = JSON.parse(json) as { sub?: unknown };
    return typeof payload?.sub === "string" ? payload.sub : "";
  } catch {
    return "";
  }
}

type PreviewTokenPayload = {
  token?: string;
  expires_seconds?: number;
};

export type SessionStatus = "loading" | "ready" | "unavailable";

export function getSessionToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return (window.localStorage.getItem(SESSION_KEY) ?? "").trim();
}

export function setSessionToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const value = token.trim();
  if (!value) {
    window.localStorage.removeItem(SESSION_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_KEY, value);
}

export function clearSessionToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(SESSION_KEY);
}

export async function issuePreviewSession(): Promise<string> {
  const sub = getOrCreatePreviewSub();
  const url = new URL(`${API_BASE}/api/auth/preview-token`);
  if (sub) {
    url.searchParams.set("sub", sub);
  }
  const { response, payload } = await fetchJson<PreviewTokenPayload>(
    url.toString()
  );
  if (!response.ok || !payload?.ok) {
    return "";
  }
  return (payload.data?.token ?? "").trim();
}

export async function ensureSession(options?: {
  envToken?: string;
  allowPreviewIssue?: boolean;
}): Promise<{ token: string; status: SessionStatus }> {
  const current = getSessionToken();
  if (current) {
    const subject = jwtSubject(current);
    if (subject && isUuid(subject)) {
      return { token: current, status: "ready" };
    }
    // Migrate older preview tokens (non-UUID sub) by forcing a re-issue.
    clearSessionToken();
  }

  const envToken = (options?.envToken ?? "").trim();
  if (envToken) {
    const subject = jwtSubject(envToken);
    if (subject && isUuid(subject)) {
      setSessionToken(envToken);
      return { token: envToken, status: "ready" };
    }
  }

  if (options?.allowPreviewIssue !== false) {
    const issued = await issuePreviewSession();
    if (issued) {
      setSessionToken(issued);
      return { token: issued, status: "ready" };
    }
  }

  return { token: "", status: "unavailable" };
}

export async function withSessionRetry<T>(
  requestWithToken: (token: string) => Promise<T>,
  options?: { envToken?: string; allowPreviewIssue?: boolean }
): Promise<T> {
  const current = getSessionToken();
  if (current) {
    try {
      return await requestWithToken(current);
    } catch (error) {
      const status = (error as { status?: number })?.status;
      if (status !== 401) {
        throw error;
      }
    }
  }

  clearSessionToken();
  const ensured = await ensureSession(options);
  if (!ensured.token) {
    throw new Error("Session unavailable");
  }
  return requestWithToken(ensured.token);
}
