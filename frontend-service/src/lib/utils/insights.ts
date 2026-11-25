// Recommendations drawn from the folders (their last measures, scans and ACL reads): computed once here, shown by
// Insights & Recommendations and by My Tasks. Each one names the express search of Storage Roots that lists its folders.
import { t } from '$lib/i18n';
import { formatBytes } from '$lib/utils/format';

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
const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);

export function buildInsights(rows: Root[], governance: boolean): Insight[] {
  const list: Insight[] = [];
  const add = (insight: Insight) => insight.count > 0 && list.push(insight);
  const cold = rows.reduce((sum, row) => sum + num(row.cold_1y_bytes), 0);
  const coldFolders = rows.filter((row) => size(row) > 0 && num(row.cold_1y_bytes) > 0.5 * size(row));
  add({ key: 'cold', big: formatBytes(cold), title: t('Cold data'), tone: 'warn', count: coldFolders.length, query: 'est:donnees-froides',
    detail: t('Untouched for more than a year; {count} folder(s) are mostly cold: candidates for the archive.', { count: coldFolders.length }) });
  const dupBytes = rows.reduce((sum, row) => sum + num(row.dup_wasted_bytes) + num(row.shared_dup_bytes), 0);
  const dupFolders = rows.filter((row) => num(row.dup_wasted_bytes) + num(row.shared_dup_bytes) > 0);
  add({ key: 'dups', big: formatBytes(dupBytes), title: t('Duplicates to free'), tone: 'warn', count: dupFolders.length, query: 'est:doublons',
    detail: t('Identical files (verified fingerprint) inside or between {count} folder(s).', { count: dupFolders.length }) });
  const secrets = rows.filter((row) => num(row.password_files) + num(row.key_files) > 0);
  add({ key: 'secrets', big: String(secrets.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0)), title: t('Passwords and keys in files'),
    tone: 'bad', count: secrets.length, query: 'est:mot-de-passe', detail: t('Found by the sensitivity scan in {count} folder(s); ask their guardians to correct.', { count: secrets.length }) });
  const corrections = rows.filter((row) => ['open', 'overdue'].includes(String(row.remediation_status ?? '')));
  add({ key: 'corrections', big: String(corrections.length), title: t('Corrections in progress'), tone: 'warn', count: corrections.length, query: 'est:correction',
    detail: t('Asked to the guardians after a sensitivity scan, some may be overdue.') });
  if (governance) {
    const noGuardian = rows.filter((row) => num(row.guardians_count) === 0);
    add({ key: 'guardian', big: String(noGuardian.length), title: t('Folders without guardian'), tone: 'warn', count: noGuardian.length, query: 'est:sans-gardien',
      detail: t('Their requests go to the administrators.') });
    const broken = rows.filter((row) => row.inheritance_broken === true);
    add({ key: 'inheritance', big: String(broken.length), title: t('Inheritance broken'), tone: 'mut', count: broken.length, query: 'est:heritage-rompu',
      detail: t('The folder keeps its own entries and no longer follows its parent.') });
  }
  const quota = rows.filter((row) => row.quota_used_percent != null && num(row.quota_used_percent) >= num(row.quota_warn_percent ?? 85));
  add({ key: 'quota', big: String(quota.length), title: t('Quotas almost full'), tone: 'warn', count: quota.length, query: 'est:quota-plein',
    detail: t('{count} space request(s) waiting', { count: rows.reduce((sum, row) => sum + num(row.quota_pending_requests), 0) }) });
  const junk = rows.filter((row) => num(row.junk_files) > 0);
  add({ key: 'junk', big: rows.reduce((sum, row) => sum + num(row.junk_files), 0).toLocaleString('fr-FR'), title: t('Clutter files'), tone: 'mut', count: junk.length,
    query: 'est:encombre', detail: t('~$*, Thumbs.db, .tmp… in {count} folder(s): they can go.', { count: junk.length }) });
  const never = rows.filter((row) => row.content_size_bytes == null && !['done', 'running'].includes(String(row.measure_status ?? '')));
  add({ key: 'never', big: String(never.length), title: t('Folders never measured'), tone: 'mut', count: never.length, query: 'est:non-mesure',
    detail: t('No detailed volume, no 5S, no duplicates for them yet.') });
  return list;
}
