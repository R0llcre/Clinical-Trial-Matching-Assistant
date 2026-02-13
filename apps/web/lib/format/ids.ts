export function shortId(value: string, len = 8): string {
  const input = (value ?? "").toString();
  if (!input) {
    return "";
  }
  const safeLen = Number.isFinite(len) && len > 0 ? Math.trunc(len) : 8;
  return input.length > safeLen ? input.slice(0, safeLen) : input;
}

