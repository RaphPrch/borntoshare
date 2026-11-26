// Recommendations drawn from the folders (their last measures, scans and ACL reads): computed once here, shown by
// Insights & Recommendations (Overview, Recommendations). Each one is the express search of Storage Roots that lists its
// folders, and says what brings it: always there, the access governance, or the 5S module (its measures of the content
// and its sensitivity scan).
import { t } from '$lib/i18n';
import { formatBytes } from '$lib/utils/format';
import { foldersMatching } from '$lib/components/storage-roots/folder-query';

type Root = Record<string, any>;
export type InsightLicense = 'core' | 'governance' | 'fives';

/** The fields of /storage-roots/context the recommendations read (its `fields` parameter: the whole list is much heavier) */
export const INSIGHT_FIELDS = [
  'storage_root_id', 'content_size_bytes', 'estimated_size_bytes', 'cold_1y_bytes', 'dup_wasted_bytes', 'shared_dup_bytes',
  'password_files', 'key_files', 'personal_files', 'bank_files', 'risky_files', 'sensitive_files', 'remediation_status',
  'guardians_count', 'backup_covered', 'inheritance_broken', 'pending_validation_count', 'needs_revalidation', 'tags',
  'quota_used_percent', 'quota_warn_percent', 'quota_pending_requests', 'junk_files', 'measure_status',
  'last_probe_status', 'last_probe_at', 'effective_availability'
].join(',');
export type Insight = { key: string; big: string; title: string; detail: string; query: string; tone: 'bad' | 'warn' | 'mut' | 'ok'; count: number;
  license: InsightLicense };

export const INSIGHT_ICONS: Record<string, string> = { cold: 'bi-snow', dups: 'bi-files', secrets: 'bi-key', corrections: 'bi-tools', guardian: 'bi-person-x',
  backup: 'bi-person-dash', inheritance: 'bi-scissors', quota: 'bi-speedometer2', junk: 'bi-trash3', never: 'bi-rulers', unreachable: 'bi-plug',
  untested: 'bi-question-circle', untagged: 'bi-tag', empty: 'bi-inbox', waiting: 'bi-hourglass-split', revalidate: 'bi-arrow-repeat',
  personal: 'bi-person-vcard', risky: 'bi-exclamation-diamond', unscanned: 'bi-search' };

const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);

export type InsightContext = { governance: boolean; fives: boolean };

/** The groups of the recommendations and of the reports, by what brings them (the same on both pages) */
export const licenseGroups = (): Array<{ key: InsightLicense; title: string; hint: string }> => [
  { key: 'core', title: t('Storage and infrastructure'), hint: t('Every installation') },
  { key: 'governance', title: t('Access governance'), hint: t('Access governance license') },
  { key: 'fives', title: t('Data quality and security'), hint: t('5S module') }
];

export function buildInsights(rows: Root[], context: InsightContext): Insight[] {
  const list: Insight[] = [];
  // Each recommendation is the express search its « See » opens: its folders are counted by that very search
  const add = (license: InsightLicense, key: string, query: string, make: (folders: Root[]) => Omit<Insight, 'key' | 'query' | 'count' | 'license'>) => {
    if ((license === 'governance' && !context.governance) || (license === 'fives' && !context.fives)) return;
    const folders = foldersMatching(rows, query);
    if (folders.length) list.push({ key, query, count: folders.length, license, ...make(folders) });
  };
  const count = (folders: Root[]) => String(folders.length);

  // Always there: reaching the folders, measuring them, classifying them, their quotas
  add('core', 'unreachable', 'est:injoignable', (folders) => ({ big: count(folders), title: t('Unreachable folders'), tone: 'bad',
    detail: t('The last test could not reach them: rights, network or a server down. Their figures are those of before.') }));
  add('core', 'quota', 'est:quota-plein', (folders) => ({ big: count(folders), title: t('Quotas almost full'), tone: 'warn',
    detail: t('{count} space request(s) waiting', { count: rows.reduce((sum, row) => sum + num(row.quota_pending_requests), 0) }) }));
  add('core', 'never', 'est:non-mesure', (folders) => ({ big: count(folders), title: t('Folders never measured'), tone: 'mut',
    detail: t('No detailed volume, no 5S, no duplicates for them yet.') }));
  add('core', 'untested', 'est:non-teste', (folders) => ({ big: count(folders), title: t('Folders never tested'), tone: 'mut',
    detail: t('BornToShare never checked it can reach them.') }));
  add('core', 'untagged', 'est:sans-tag', (folders) => ({ big: count(folders), title: t('Folders not classified'), tone: 'mut',
    detail: t('Without a tag they escape the policies and the reports by tag.') }));
  add('core', 'empty', 'est:vide', (folders) => ({ big: count(folders), title: t('Empty folders'), tone: 'mut',
    detail: t('Measured at zero: still used, or to close?') }));

  // The access governance: who answers for the folders, what waits for them
  add('governance', 'guardian', 'est:sans-gardien', (folders) => ({ big: count(folders), title: t('Folders without guardian'), tone: 'warn',
    detail: t('Their requests go to the administrators.') }));
  add('governance', 'backup', 'est:sans-suppleant', (folders) => ({ big: count(folders), title: t('One guardian, no backup'), tone: 'warn',
    detail: t('When their guardian is away, nobody can decide on their requests.') }));
  add('governance', 'waiting', 'est:demandes', (folders) => ({ big: String(folders.reduce((sum, row) => sum + num(row.pending_validation_count), 0)),
    title: t('Requests waiting'), tone: 'warn', detail: t('In {count} folder(s), waiting for their guardians.', { count: folders.length }) }));
  add('governance', 'revalidate', 'est:a-revalider', (folders) => ({ big: count(folders), title: t('Folders to revalidate'), tone: 'warn',
    detail: t('Their accesses are due for a check by their guardians.') }));
  add('governance', 'inheritance', 'est:heritage-rompu', (folders) => ({ big: count(folders), title: t('Inheritance broken'), tone: 'mut',
    detail: t('The folder keeps its own entries and no longer follows its parent.') }));

  // The 5S module: what its measures (age, duplicates, clutter) and its sensitivity scan find in the content
  add('fives', 'secrets', 'est:secret', (folders) => ({ big: String(folders.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0)),
    title: t('Passwords and keys in files'), tone: 'bad', detail: t('Found by the sensitivity scan in {count} folder(s); ask their guardians to correct.', { count: folders.length }) }));
  add('fives', 'personal', 'est:donnees-personnelles', (folders) => ({ big: String(folders.reduce((sum, row) => sum + num(row.personal_files), 0)),
    title: t('Personal data'), tone: 'warn', detail: t('Files with personal data (GDPR) in {count} folder(s): who may read them?', { count: folders.length }) }));
  add('fives', 'risky', 'est:fichiers-a-risque', (folders) => ({ big: String(folders.reduce((sum, row) => sum + num(row.risky_files), 0)),
    title: t('Risky files'), tone: 'warn', detail: t('Database backups, mailboxes or executables stored in {count} folder(s).', { count: folders.length }) }));
  add('fives', 'corrections', 'est:correction', (folders) => ({ big: count(folders), title: t('Corrections in progress'), tone: 'warn',
    detail: t('Asked to the guardians after a sensitivity scan, some may be overdue.') }));
  add('fives', 'cold', 'est:donnees-froides', (folders) => ({ big: formatBytes(rows.reduce((sum, row) => sum + num(row.cold_1y_bytes), 0)), title: t('Cold data'), tone: 'warn',
    detail: t('Untouched for more than a year; {count} folder(s) are mostly cold: candidates for the archive.', { count: folders.length }) }));
  add('fives', 'dups', 'est:doublons', (folders) => ({ big: formatBytes(folders.reduce((sum, row) => sum + num(row.dup_wasted_bytes) + num(row.shared_dup_bytes), 0)),
    title: t('Duplicates to free'), tone: 'warn', detail: t('Identical files (verified fingerprint) inside or between {count} folder(s).', { count: folders.length }) }));
  add('fives', 'junk', 'est:encombre', (folders) => ({ big: folders.reduce((sum, row) => sum + num(row.junk_files), 0).toLocaleString('fr-FR'), title: t('Clutter files'), tone: 'mut',
    detail: t('~$*, Thumbs.db, .tmp… in {count} folder(s): they can go.', { count: folders.length }) }));
  add('fives', 'unscanned', 'est:non-analyse', (folders) => ({ big: count(folders), title: t('Never scanned for sensitivity'), tone: 'mut',
    detail: t('Nobody knows yet whether they hold passwords or personal data.') }));
  // The most pressing first: bad, then warn, then the rest
  const order = { bad: 0, warn: 1, mut: 2, ok: 3 } as const;
  return list.sort((a, b) => order[a.tone] - order[b.tone]);
}
