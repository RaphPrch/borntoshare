/**
 * Coverage of the data (Insights & Recommendations › Overview): parts of a whole, each opening the list of what is
 * missing. Counted with the express searches of Storage Roots (the figure = the list). Pure, tested.
 */
import { t } from '$lib/i18n';
import { foldersMatching } from '$lib/components/storage-roots/folder-query';
import { percent } from '$lib/utils/ring';

export type CoverageRing = { key: string; label: string; value: number | null; detail: string; href: string };
export type ExposureSummary = Record<string, number>;
export type TopologySummary = { servers: number; dfs: number; states: Record<string, number> };

const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const search = (query: string) => `/storage-roots?q=${encodeURIComponent(query)}`;

export function coverageRings(input: {
  roots: Record<string, any>[] | null;
  governance: boolean;
  /** null: still reading; undefined: not for this person (the ring is left out) */
  exposure?: ExposureSummary | null;
  topology?: TopologySummary | null;
}): CoverageRing[] {
  const roots = input.roots ?? [];
  const total = roots.length;
  const never = input.roots ? foldersMatching(roots, 'est:non-mesure').length : 0;
  const rings: CoverageRing[] = [
    { key: 'measured', label: t('Folders measured'), value: input.roots ? percent(total - never, total) : null,
      detail: t('{count} never measured', { count: never }), href: search('est:non-mesure') }
  ];
  if (input.governance) {
    const without = input.roots ? foldersMatching(roots, 'est:sans-gardien').length : 0;
    rings.push({ key: 'guardian', label: t('Folders with a guardian'), value: input.roots ? percent(total - without, total) : null,
      detail: t('{count} without guardian', { count: without }), href: search('est:sans-gardien') });
    if (input.exposure !== undefined) {
      const e = input.exposure;
      rings.push({ key: 'governed', label: t('Folders governed'), value: e ? percent(num(e.governed), num(e.total) - num(e.unknown)) : null,
        detail: e ? t('{open} open to everyone · {outside} outside accounts', { open: num(e.open_write) + num(e.open_read), outside: num(e.outside) }) : t('Reading the ACLs…'),
        href: '/insights/exposure' });
    }
  }
  if (input.topology !== undefined) {
    const topo = input.topology;
    const states = topo?.states ?? {};
    rings.push({ key: 'servers', label: t('Servers available'),
      value: topo ? percent(num(states.available), num(topo.servers) + num(topo.dfs) - num(states.unknown)) : null,
      detail: topo ? t('{degraded} degraded · {down} unavailable', { degraded: num(states.degraded), down: num(states.unavailable) }) : t('Reading the topology…'),
      href: '/insights/topology' });
  }
  return rings;
}
