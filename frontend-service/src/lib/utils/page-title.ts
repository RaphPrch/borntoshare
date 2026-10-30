import { t } from '$lib/i18n';

// Browser tab title per route (longest matching prefix wins). Labels are translated when read.
const TITLES: [prefix: string, label: string][] = [
  ['/dashboard', 'Dashboard'],
  ['/storage-roots', 'Folders'],
  ['/access-requests/', 'Access request'],
  ['/access-requests', 'Access requests'],
  ['/admin/zones', 'Zones'],
  ['/admin/storage-endpoints', 'File servers'],
  ['/admin/identity-sources', 'Directories'],
  ['/admin/identity', 'Identities'],
  ['/admin/tags', 'Tags'],
  ['/observability', 'Monitoring'],
  ['/admin/advanced-settings', 'Settings']
];

const matches = (pathname: string, prefix: string): boolean =>
  prefix.endsWith('/')
    ? pathname.startsWith(prefix) && pathname.length > prefix.length
    : pathname === prefix || pathname.startsWith(`${prefix}/`);

export const pageTitle = (pathname: string, alertsCount = 0): string => {
  const match = TITLES.filter(([prefix]) => matches(pathname, prefix)).sort((a, b) => b[0].length - a[0].length)[0];
  const base = match ? `${t(match[1])} · BornToShare` : 'BornToShare';
  return alertsCount > 0 ? `(${alertsCount}) ${base}` : base;
};
