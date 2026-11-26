// Recommendations drawn from the folders (their last measures, scans and ACL reads): computed once here, shown by
// Insights & Recommendations and the Dashboard. Each one names the express search of Storage Roots that lists its folders.
import { t } from '$lib/i18n';
import { formatBytes } from '$lib/utils/format';
import { foldersMatching } from '$lib/components/storage-roots/folder-query';

type Root = Record<string, any>;

/** The fields of /storage-roots/context the recommendations read (its `fields` parameter: the whole list is much heavier) */
export const INSIGHT_FIELDS = [
  'storage_root_id', 'content_size_bytes', 'estimated_size_bytes', 'cold_1y_bytes', 'dup_wasted_bytes', 'shared_dup_bytes',
  'password_files', 'key_files', 'remediation_status', 'guardians_count', 'inheritance_broken', 'quota_used_percent',
  'quota_warn_percent', 'quota_pending_requests', 'junk_files', 'measure_status'
].join(',');
export type Insight = { key: string; big: string; title: string; detail: string; query: string; tone: 'bad' | 'warn' | 'mut' | 'ok'; count: number };

export const INSIGHT_ICONS: Record<string, string> = { cold: 'bi-snow', dups: 'bi-files', secrets: 'bi-key', corrections: 'bi-tools', guardian: 'bi-person-x',
  inheritance: 'bi-scissors', quota: 'bi-speedometer2', junk: 'bi-trash3', never: 'bi-rulers' };

const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);

export function buildInsights(rows: Root[], governance: boolean): Insight[] {
  const list: Insight[] = [];
  // Each recommendation is the express search its « See » opens: its folders are counted by that very search
  const add = (key: string, query: string, make: (folders: Root[]) => Omit<Insight, 'key' | 'query' | 'count'>) => {
    const folders = foldersMatching(rows, query);
    if (folders.length) list.push({ key, query, count: folders.length, ...make(folders) });
  };
  add('cold', 'est:donnees-froides', (folders) => ({ big: formatBytes(rows.reduce((sum, row) => sum + num(row.cold_1y_bytes), 0)), title: t('Cold data'), tone: 'warn',
    detail: t('Untouched for more than a year; {count} folder(s) are mostly cold: candidates for the archive.', { count: folders.length }) }));
  add('dups', 'est:doublons', (folders) => ({ big: formatBytes(folders.reduce((sum, row) => sum + num(row.dup_wasted_bytes) + num(row.shared_dup_bytes), 0)),
    title: t('Duplicates to free'), tone: 'warn', detail: t('Identical files (verified fingerprint) inside or between {count} folder(s).', { count: folders.length }) }));
  add('secrets', 'est:secret', (folders) => ({ big: String(folders.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0)),
    title: t('Passwords and keys in files'), tone: 'bad', detail: t('Found by the sensitivity scan in {count} folder(s); ask their guardians to correct.', { count: folders.length }) }));
  add('corrections', 'est:correction', (folders) => ({ big: String(folders.length), title: t('Corrections in progress'), tone: 'warn',
    detail: t('Asked to the guardians after a sensitivity scan, some may be overdue.') }));
  if (governance) {
    add('guardian', 'est:sans-gardien', (folders) => ({ big: String(folders.length), title: t('Folders without guardian'), tone: 'warn',
      detail: t('Their requests go to the administrators.') }));
    add('inheritance', 'est:heritage-rompu', (folders) => ({ big: String(folders.length), title: t('Inheritance broken'), tone: 'mut',
      detail: t('The folder keeps its own entries and no longer follows its parent.') }));
  }
  add('quota', 'est:quota-plein', (folders) => ({ big: String(folders.length), title: t('Quotas almost full'), tone: 'warn',
    detail: t('{count} space request(s) waiting', { count: rows.reduce((sum, row) => sum + num(row.quota_pending_requests), 0) }) }));
  add('junk', 'est:encombre', (folders) => ({ big: folders.reduce((sum, row) => sum + num(row.junk_files), 0).toLocaleString('fr-FR'), title: t('Clutter files'), tone: 'mut',
    detail: t('~$*, Thumbs.db, .tmp… in {count} folder(s): they can go.', { count: folders.length }) }));
  add('never', 'est:non-mesure', (folders) => ({ big: String(folders.length), title: t('Folders never measured'), tone: 'mut',
    detail: t('No detailed volume, no 5S, no duplicates for them yet.') }));
  return list;
}
