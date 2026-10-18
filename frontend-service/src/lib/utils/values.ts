// Small value helpers shared across modules and components.

/** The value as a plain object, or null for anything else (null, arrays, primitives). */
export const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

/** Trimmed, lower-cased text for case-insensitive comparisons and search. */
export const normalizeText = (value: unknown): string => String(value ?? '').trim().toLowerCase();

export const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

export const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));
