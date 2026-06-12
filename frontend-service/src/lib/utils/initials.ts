export const initialsFromLabel = (value?: string | null, fallback = '??'): string => {
  const raw = String(value ?? '').trim();
  if (!raw) return fallback;
  const parts = raw.split(/\s+/).filter(Boolean);
  const first = (parts[0]?.[0] ?? '').toUpperCase();
  const second = (parts[1]?.[0] ?? parts[0]?.[1] ?? '').toUpperCase();
  return `${first}${second}`.trim() || fallback;
};

