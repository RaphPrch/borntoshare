import { t } from '$lib/i18n';

/**
 * Express search of the folders list: free text plus filters written « key:value ».
 *   tag:Finance  gardien:alice  zone:CORP  serveur:FILER01  dfs:brest  partage:RH
 *   est:alerte | injoignable | sain | sans-gardien | sans-tag | heritage-rompu | demandes | a-revalider | vide | non-mesure
 *   alerte:acl  taille>1Go  taille<10Mo
 * A leading « - » excludes (-tag:Archive); a value with spaces goes in quotes (tag:"Données RH").
 */
type Row = Record<string, any>;
export type QueryFilter = { key: string; op: ':' | '>' | '<'; value: string; neg: boolean; raw: string };
export type Suggestion = { insert: string; label: string; hint: string; icon: string };

const ALIASES: Record<string, string> = {
  tag: 'tag', tags: 'tag', etiquette: 'tag',
  gardien: 'guardian', guardian: 'guardian', g: 'guardian',
  zone: 'zone', z: 'zone',
  serveur: 'server', server: 'server', filer: 'server',
  dfs: 'dfs', namespace: 'dfs',
  partage: 'share', share: 'share',
  est: 'is', is: 'is', etat: 'is',
  alerte: 'alert', alert: 'alert',
  taille: 'size', size: 'size'
};

const fold = (value: unknown) => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const TOKEN = /(-?)([a-zA-Zéèêà]+)([:<>])("[^"]*"?|\S*)/y;

export function parseFolderQuery(query: string): { filters: QueryFilter[]; text: string } {
  const filters: QueryFilter[] = [];
  const words: string[] = [];
  let index = 0;
  const source = String(query ?? '');
  while (index < source.length) {
    if (/\s/.test(source[index])) {
      index += 1;
      continue;
    }
    TOKEN.lastIndex = index;
    const match = TOKEN.exec(source);
    const key = match ? ALIASES[fold(match[2])] : undefined;
    if (match && key && match[4] !== '') {
      filters.push({ key, op: match[3] as QueryFilter['op'], value: match[4].replace(/^"|"$/g, ''), neg: match[1] === '-', raw: match[0] });
      index = TOKEN.lastIndex;
      continue;
    }
    const end = source.slice(index).search(/\s/);
    const word = end < 0 ? source.slice(index) : source.slice(index, index + end);
    // « tag: » still being typed: not a word to look for
    if (!(match && key && match[4] === '')) words.push(word);
    index += word.length || 1;
  }
  return { filters, text: words.join(' ') };
}

const UNITS: Record<string, number> = { o: 1, b: 1, ko: 1024, kb: 1024, mo: 1024 ** 2, mb: 1024 ** 2, go: 1024 ** 3, gb: 1024 ** 3, to: 1024 ** 4, tb: 1024 ** 4 };
const bytesOf = (value: string): number | null => {
  const match = fold(value).replace(',', '.').match(/^(\d+(?:\.\d+)?)\s*([a-z]*)$/);
  if (!match) return null;
  const unit = UNITS[match[2] || 'o'];
  return unit ? Number(match[1]) * unit : null;
};

export const tagNames = (row: Row): string[] =>
  (Array.isArray(row?.tags) ? row.tags : []).map((tag: any) => String(tag?.label ?? tag?.name ?? tag?.code ?? '')).filter(Boolean);
const guardians = (row: Row): string[] => (Array.isArray(row?.guardian_names) ? row.guardian_names.map(String) : []);
const pathParts = (row: Row) => String(row?.root_path ?? '').split(/[\\/]+/).filter(Boolean);
const alertTypes = (row: Row) => String(row?.open_alert_types ?? '').split(',').filter(Boolean);
const dfsNamespace = (row: Row) => String(row?.dfs_path ?? '').split(/[\\/]+/).filter(Boolean)[1] ?? '';
const size = (row: Row): number | null => {
  const value = row?.content_size_bytes ?? row?.estimated_size_bytes;
  return value == null || value === '' ? null : Number(value);
};

const STATES: Record<string, (row: Row) => boolean> = {
  alerte: (row) => Number(row?.open_alerts_count ?? 0) > 0,
  injoignable: (row) => String(row?.effective_availability ?? '').includes('unreachable') || row?.last_probe_status === 'failed',
  sain: (row) => Number(row?.open_alerts_count ?? 0) === 0 && row?.last_probe_status === 'success',
  'sans-gardien': (row) => Number(row?.guardians_count ?? 0) === 0,
  'sans-tag': (row) => tagNames(row).length === 0,
  'heritage-rompu': (row) => row?.inheritance_broken === true,
  demandes: (row) => Number(row?.pending_validation_count ?? 0) > 0,
  'a-revalider': (row) => row?.needs_revalidation === true,
  vide: (row) => size(row) === 0,
  'non-mesure': (row) => size(row) == null,
  'non-teste': (row) => !row?.last_probe_at,
  dfs: (row) => Boolean(row?.dfs_path),
  sensible: (row) => Number(row?.sensitive_files ?? 0) > 0,
  'non-analyse': (row) => row?.sensitive_files == null,
  'mot-de-passe': (row) => Number(row?.password_files ?? 0) > 0,
  quota: (row) => row?.quota_limit_bytes != null,
  'sans-quota': (row) => row?.quota_limit_bytes == null,
  'quota-plein': (row) => row?.quota_used_percent != null && Number(row.quota_used_percent) >= Number(row?.quota_warn_percent ?? 85),
  'quota-demande': (row) => Number(row?.quota_pending_requests ?? 0) > 0
};

function test(row: Row, filter: QueryFilter): boolean {
  const wanted = fold(filter.value);
  const has = (values: unknown[]) => values.some((value) => fold(value).includes(wanted));
  switch (filter.key) {
    case 'tag':
      return has(tagNames(row));
    case 'guardian':
      return has(guardians(row));
    case 'zone':
      return has([row?.zone_name]);
    case 'server':
      return has([row?.storage_endpoint_name, row?.storage_endpoint_host, pathParts(row)[0]]);
    case 'dfs':
      return has([row?.dfs_path]);
    case 'share':
      return has([pathParts(row)[1]]);
    case 'alert':
      return has(alertTypes(row));
    case 'is':
      return (STATES[wanted.replace(/\s+/g, '-')] ?? (() => false))(row);
    case 'size': {
      const limit = bytesOf(filter.value);
      const value = size(row);
      if (limit == null || value == null) return false;
      return filter.op === '<' ? value < limit : filter.op === '>' ? value > limit : value === limit;
    }
    default:
      return true;
  }
}

export const matchesFolderQuery = (row: Row, filters: QueryFilter[]): boolean =>
  filters.every((filter) => test(row, filter) !== filter.neg);

const quote = (value: string) => (/\s/.test(value) ? `"${value}"` : value);
const STATE_LABELS = (): Array<[string, string]> => [
  ['alerte', t('with open alerts')],
  ['injoignable', t('unreachable')],
  ['sain', t('healthy')],
  ['sans-gardien', t('without guardian')],
  ['sans-tag', t('without tag')],
  ['heritage-rompu', t('inheritance broken')],
  ['demandes', t('with pending requests')],
  ['a-revalider', t('to revalidate')],
  ['vide', t('empty')],
  ['non-mesure', t('size not measured')],
  ['non-teste', t('never tested')],
  ['dfs', t('reached through DFS')],
  ['sensible', t('with sensitive files')],
  ['non-analyse', t('never scanned for sensitivity')],
  ['mot-de-passe', t('with passwords stored')],
  ['quota', t('with a quota')],
  ['sans-quota', t('without quota')],
  ['quota-plein', t('quota almost full')],
  ['quota-demande', t('quota request waiting')]
];

/** What the list knows, per key: the values to propose */
function vocabulary(rows: Row[], tags: string[]) {
  const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr', { numeric: true }));
  return {
    tag: unique([...tags, ...rows.flatMap(tagNames)]),
    guardian: unique(rows.flatMap((row) => guardians(row).slice(0, 1))),
    zone: unique(rows.map((row) => String(row?.zone_name ?? ''))),
    server: unique(rows.map((row) => String(row?.storage_endpoint_name ?? ''))),
    dfs: unique(rows.map(dfsNamespace)),
    share: unique(rows.map((row) => pathParts(row)[1] ?? '')),
    alert: unique(rows.flatMap(alertTypes))
  };
}

const KEY_META = (): Record<string, { word: string; label: string; icon: string }> => ({
  tag: { word: 'tag', label: t('Tag'), icon: 'bi-tag' },
  guardian: { word: 'gardien', label: t('Guardian'), icon: 'bi-person-check' },
  zone: { word: 'zone', label: t('Zone'), icon: 'bi-geo-alt' },
  server: { word: 'serveur', label: t('Server'), icon: 'bi-hdd-network' },
  dfs: { word: 'dfs', label: t('DFS namespace'), icon: 'bi-diagram-3' },
  share: { word: 'partage', label: t('Share'), icon: 'bi-folder-symlink' },
  alert: { word: 'alerte', label: t('Alert'), icon: 'bi-exclamation-triangle' }
});

/** Proposals for the word being typed (the last one of the query) */
export function folderSuggestions(query: string, rows: Row[], tags: string[] = []): Suggestion[] {
  const last = String(query ?? '').split(/\s+/).pop() ?? '';
  // The filter already typed in full: nothing more to propose
  return suggestionsFor(last, rows, tags).filter((item) => fold(item.insert) !== fold(last));
}

function suggestionsFor(last: string, rows: Row[], tags: string[]): Suggestion[] {
  const vocab = vocabulary(rows, tags);
  const meta = KEY_META();
  const typed = last.match(/^-?([a-zA-Zéèêà]+):(.*)$/);
  if (typed) {
    const key = ALIASES[fold(typed[1])];
    const part = fold(typed[2].replace(/^"/, ''));
    const prefix = last.startsWith('-') ? '-' : '';
    if (key === 'is') {
      return STATE_LABELS()
        .filter(([value, label]) => !part || value.includes(part) || fold(label).includes(part))
        .map(([value, label]) => ({ insert: `${prefix}est:${value}`, label, hint: `est:${value}`, icon: 'bi-funnel' }));
    }
    const values = key ? (vocab as Record<string, string[]>)[key] : null;
    if (!values || !key) return [];
    return values
      .filter((value) => !part || fold(value).includes(part))
      .slice(0, 12)
      .map((value) => ({ insert: `${prefix}${meta[key].word}:${quote(value)}`, label: value, hint: meta[key].label, icon: meta[key].icon }));
  }
  const word = fold(last);
  if (word.length < 2) return [];
  // A plain word: the tags, guardians, zones… that contain it
  const out: Suggestion[] = [];
  for (const [key, values] of Object.entries(vocab)) {
    for (const value of values) {
      if (fold(value).includes(word)) out.push({ insert: `${meta[key].word}:${quote(value)}`, label: value, hint: meta[key].label, icon: meta[key].icon });
    }
  }
  for (const [value, label] of STATE_LABELS()) {
    if (fold(label).includes(word) || value.includes(word)) out.push({ insert: `est:${value}`, label, hint: t('State'), icon: 'bi-funnel' });
  }
  return out.slice(0, 10);
}

/** Starting points shown before typing */
export const folderQueryExamples = (): Suggestion[] => [
  { insert: 'tag:', label: t('By tag'), hint: 'tag:Finance', icon: 'bi-tag' },
  { insert: 'gardien:', label: t('By guardian'), hint: 'gardien:alice', icon: 'bi-person-check' },
  { insert: 'est:sensible', label: t('With sensitive files'), hint: 'est:sensible', icon: 'bi-shield-lock' },
  { insert: 'est:mot-de-passe', label: t('With passwords stored'), hint: 'est:mot-de-passe', icon: 'bi-key' },
  { insert: 'est:quota-plein', label: t('Quota almost full'), hint: 'est:quota-plein', icon: 'bi-speedometer2' },
  { insert: 'est:sans-gardien', label: t('Without guardian'), hint: 'est:sans-gardien', icon: 'bi-person-x' },
  { insert: 'est:alerte', label: t('With open alerts'), hint: 'est:alerte', icon: 'bi-exclamation-triangle' },
  { insert: 'est:sans-tag', label: t('Without tag'), hint: 'est:sans-tag', icon: 'bi-tag' },
  { insert: 'est:heritage-rompu', label: t('Inheritance broken'), hint: 'est:heritage-rompu', icon: 'bi-scissors' },
  { insert: 'dfs:', label: t('By DFS namespace'), hint: 'dfs:brest', icon: 'bi-diagram-3' },
  { insert: 'serveur:', label: t('By server'), hint: 'serveur:FILER01', icon: 'bi-hdd-network' },
  { insert: 'taille>1Go', label: t('Larger than 1 GB'), hint: 'taille>1Go', icon: 'bi-hdd' },
  { insert: 'est:', label: t('By state'), hint: 'est:injoignable', icon: 'bi-funnel' }
];

/** Replace the word being typed by the chosen suggestion */
export function applySuggestion(query: string, insert: string): string {
  const parts = String(query ?? '').split(/(\s+)/);
  const last = parts[parts.length - 1] ?? '';
  const keep = /^-?[a-zA-Zéèêà]+:/.test(last) || last.length >= 2 ? parts.slice(0, -1).join('') : String(query ?? '');
  const base = keep && !/\s$/.test(keep) ? `${keep} ` : keep;
  return `${base}${insert}${insert.endsWith(':') ? '' : ' '}`;
}

export const removeFilter = (query: string, raw: string): string =>
  String(query ?? '').replace(raw, '').replace(/\s{2,}/g, ' ').trim();
