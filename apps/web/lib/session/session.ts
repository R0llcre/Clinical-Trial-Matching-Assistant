import { API_BASE, fetchJson } from "../http/client";

export const SESSION_KEY = "ctmatch.jwt";

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
  const { response, payload } = await fetchJson<PreviewTokenPayload>(
    `${API_BASE}/api/auth/preview-token`
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
    return { token: current, status: "ready" };
  }

  const envToken = (options?.envToken ?? "").trim();
  if (envToken) {
    setSessionToken(envToken);
    return { token: envToken, status: "ready" };
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
