/**
 * Events of an entity for the activity timeline: one category per event, grouped by day,
 * and the figures of the last 30 days. Pure functions: the wording comes from formatActivityItem.
 */
export type ActivityCategory = 'access' | 'config' | 'check' | 'failure';

const text = (...values: unknown[]): string => {
  for (const value of values) {
    if (value == null) continue;
    const s = String(value).trim();
    if (s) return s;
  }
  return '';
};

export const eventTime = (entry: any): number | null => {
  const raw = text(entry?.event_time, entry?.created_at, entry?.timestamp);
  const ms = raw ? Date.parse(raw) : NaN;
  return Number.isFinite(ms) ? ms : null;
};

export function categoryOf(entry: any): ActivityCategory {
  const action = text(entry?.action, entry?.type).toLowerCase();
  const outcome = text(entry?.outcome, entry?.result).toLowerCase();
  const severity = text(entry?.severity).toLowerCase();
  if (['failed', 'failure', 'error'].includes(outcome) || ['critical', 'error'].includes(severity) || action.includes('failed')) return 'failure';
  if (action.startsWith('access_request') || action.includes('revoke') || action.includes('granted') || action.includes('access.')) return 'access';
  if (action.includes('probe') || action.startsWith('test_') || action.includes('dfs_read') || action.includes('check') || action.includes('sync') || action.includes('snapshot')) return 'check';
  return 'config';
}

export const isRevocation = (entry: any): boolean => /revok|revoc|removed_from_group|access_removed/.test(text(entry?.action).toLowerCase());

export function activitySummary(items: any[], now = Date.now()) {
  const since = now - 30 * 86_400_000;
  const recent = items.filter((entry) => (eventTime(entry) ?? 0) >= since);
  const access = recent.filter((entry) => categoryOf(entry) === 'access');
  return {
    granted: access.filter((entry) => !isRevocation(entry) && /approv|grant|executed|applied/.test(text(entry?.action).toLowerCase())).length,
    revoked: access.filter(isRevocation).length,
    config: recent.filter((entry) => categoryOf(entry) === 'config').length,
    failures: recent.filter((entry) => categoryOf(entry) === 'failure').length
  };
}

/** Local day key (YYYY-MM-DD) of an event, for the groups of the timeline */
export const dayKey = (ms: number): string => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export function groupByDay<T extends { ms: number | null }>(rows: T[]): Array<{ key: string; ms: number | null; rows: T[] }> {
  const groups: Array<{ key: string; ms: number | null; rows: T[] }> = [];
  for (const row of [...rows].sort((a, b) => (b.ms ?? 0) - (a.ms ?? 0))) {
    const key = row.ms == null ? 'unknown' : dayKey(row.ms);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.rows.push(row);
    else groups.push({ key, ms: row.ms, rows: [row] });
  }
  return groups;
}

/** Changed values of an event: before / after of its context, when it has them */
export function changedValues(entry: any): Array<{ key: string; before: string; after: string }> {
  const ctx = (entry?.context_json && typeof entry.context_json === 'object' ? entry.context_json : null) ?? {};
  const before = (ctx.before && typeof ctx.before === 'object' ? ctx.before : {}) as Record<string, unknown>;
  const after = (ctx.after && typeof ctx.after === 'object' ? ctx.after : {}) as Record<string, unknown>;
  const show = (value: unknown) => (value == null || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value));
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((key) => !/secret|password|hash/i.test(key))
    .filter((key) => show(before[key]) !== show(after[key]))
    .map((key) => ({ key, before: show(before[key]), after: show(after[key]) }));
}
