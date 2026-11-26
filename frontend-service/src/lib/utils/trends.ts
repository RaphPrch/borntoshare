/**
 * Trends of the data indicators (Insights & Recommendations › Overview), from the daily snapshots of core-service
 * (/insights/history). Pure, tested: a day where a part was not read (null) is a gap, not a zero.
 */
export type HistoryPoint = Record<string, any> & { day: string };
export type Trend = {
  key: string;
  label: string;
  kind: 'percent' | 'bytes' | 'count';
  goodWhen: 'up' | 'down';
  points: number[];
  last: number | null;
  /** last - first over the window (null with fewer than two days) */
  delta: number | null;
  href: string;
};

const share = (part: number, whole: number) => (whole > 0 ? (100 * part) / whole : null);
const exposureRead = (e: Record<string, number> | null | undefined) =>
  e ? ['governed', 'open_read', 'open_write', 'outside'].reduce((sum, key) => sum + Number(e[key] ?? 0), 0) : 0;
const serversKnown = (s: Record<string, number> | null | undefined) =>
  s ? ['available', 'degraded', 'unavailable'].reduce((sum, key) => sum + Number(s[key] ?? 0), 0) : 0;

type Def = Omit<Trend, 'points' | 'last' | 'delta'> & { value: (point: HistoryPoint) => number | null };

const search = (query: string) => `/storage-roots?q=${encodeURIComponent(query)}`;

export const TREND_DEFS: Def[] = [
  { key: 'measured', label: 'Folders measured', kind: 'percent', goodWhen: 'up', href: search('est:non-mesure'),
    value: (p) => share(Number(p.measured ?? 0), Number(p.folders ?? 0)) },
  { key: 'guardian', label: 'Folders with a guardian', kind: 'percent', goodWhen: 'up', href: search('est:sans-gardien'),
    value: (p) => share(Number(p.with_guardian ?? 0), Number(p.folders ?? 0)) },
  { key: 'governed', label: 'Folders governed', kind: 'percent', goodWhen: 'up', href: '/insights/exposure',
    value: (p) => (p.exposure ? share(Number(p.exposure.governed ?? 0), exposureRead(p.exposure)) : null) },
  { key: 'servers', label: 'Servers available', kind: 'percent', goodWhen: 'up', href: '/insights/topology',
    value: (p) => (p.servers ? share(Number(p.servers.available ?? 0) + Number(p.servers.degraded ?? 0), serversKnown(p.servers)) : null) },
  { key: 'volume', label: 'Measured volume', kind: 'bytes', goodWhen: 'down', href: '/storage-roots', value: (p) => Number(p.volume_bytes ?? 0) },
  { key: 'cold', label: 'Cold data', kind: 'bytes', goodWhen: 'down', href: search('est:donnees-froides'), value: (p) => Number(p.cold_bytes ?? 0) },
  { key: 'dups', label: 'Duplicates to free', kind: 'bytes', goodWhen: 'down', href: search('est:doublons'), value: (p) => Number(p.dup_bytes ?? 0) },
  { key: 'secrets', label: 'Folders with passwords or keys', kind: 'count', goodWhen: 'down', href: search('est:secret'), value: (p) => Number(p.secret_folders ?? 0) },
  { key: 'alerts', label: 'Open alerts', kind: 'count', goodWhen: 'down', href: search('est:alerte'), value: (p) => Number(p.open_alerts ?? 0) }
];

export function buildTrends(history: HistoryPoint[]): Trend[] {
  return TREND_DEFS.map(({ value, ...def }) => {
    const points = history.map(value).filter((v): v is number => v != null && Number.isFinite(v));
    return {
      ...def,
      points,
      last: points.length ? points[points.length - 1] : null,
      delta: points.length >= 2 ? points[points.length - 1] - points[0] : null
    };
  });
}

/** The direction of the change, in the words of the indicator: better, worse, or steady. */
export function trendVerdict(trend: Trend): 'better' | 'worse' | 'steady' | null {
  if (trend.delta == null) return null;
  const epsilon = trend.kind === 'percent' ? 0.05 : 0;
  if (Math.abs(trend.delta) <= epsilon) return 'steady';
  return (trend.delta > 0) === (trend.goodWhen === 'up') ? 'better' : 'worse';
}
