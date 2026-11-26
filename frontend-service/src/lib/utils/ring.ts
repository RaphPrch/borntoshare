/**
 * Circular KPIs (RingStat): a part of a whole, never a raw count. Pure, tested.
 */
export type RingTone = 'ok' | 'warn' | 'bad' | 'accent' | 'idle';

/** part / whole in %, or null when the whole is not known (nothing to show, not 0 %). */
export function percent(part: number | null | undefined, whole: number | null | undefined): number | null {
  if (part == null || whole == null || !Number.isFinite(part) || !Number.isFinite(whole) || whole <= 0) return null;
  return Math.max(0, Math.min(100, (100 * part) / whole));
}

/** stroke-dasharray of an arc of `value` % on a circle of radius r. */
export function ringDash(value: number | null | undefined, r: number): string {
  const c = 2 * Math.PI * r;
  const share = Math.max(0, Math.min(100, Number(value ?? 0)));
  return `${((c * share) / 100).toFixed(1)} ${c.toFixed(1)}`;
}

/** A coverage: good from `ok`, to watch from `warn`, bad below; unknown is idle. */
export function coverageTone(value: number | null | undefined, ok = 90, warn = 60): RingTone {
  if (value == null) return 'idle';
  return value >= ok ? 'ok' : value >= warn ? 'warn' : 'bad';
}
