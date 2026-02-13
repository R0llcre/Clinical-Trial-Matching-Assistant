export const HIDDEN_PREFIX = "__hidden__:";

export const isHiddenText = (value: string) => {
  return value.trim().startsWith(HIDDEN_PREFIX);
};

export const asHiddenText = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return HIDDEN_PREFIX;
  }
  return `${HIDDEN_PREFIX} ${trimmed}`;
};

export const stripHiddenText = (value: string) => {
  const trimmed = value.trim();
  if (!isHiddenText(trimmed)) {
    return trimmed;
  }
  return trimmed.slice(HIDDEN_PREFIX.length).trim();
};

