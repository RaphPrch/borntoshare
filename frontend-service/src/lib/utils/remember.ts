/**
 * Choices of a list kept between visits (filters, sort, page size), per browser: the list reopens as it was left.
 * Only the keys of `defaults` are read back, and only with the same type; anything else falls back to the default.
 */
const PREFIX = 'b2s:list:';

export function recall<T extends Record<string, unknown>>(key: string, defaults: T): T {
  if (typeof localStorage === 'undefined') return { ...defaults };
  try {
    const stored = JSON.parse(localStorage.getItem(PREFIX + key) ?? 'null') as Record<string, unknown> | null;
    if (!stored || typeof stored !== 'object') return { ...defaults };
    const out = { ...defaults } as Record<string, unknown>;
    for (const [name, fallback] of Object.entries(defaults)) {
      if (name in stored && typeof stored[name] === typeof fallback) out[name] = stored[name];
    }
    return out as T;
  } catch {
    return { ...defaults };
  }
}

export function remember(key: string, value: Record<string, unknown>): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* private window or full storage: the list simply does not remember */
  }
}
