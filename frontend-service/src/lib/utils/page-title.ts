// Browser tab title per route (longest matching prefix wins): the name of the menu entry, a product name the same in both languages.
const TITLES: [prefix: string, label: string][] = [
  ['/dashboard', 'Dashboard'],
  ['/pilot', 'Pilot'],
  ['/storage-roots', 'Storage Roots'],
  ['/access-requests', 'Access Management'],
  ['/exposure', 'Access Management'],
  ['/access-reviews', 'Access Management'],
  ['/observability', 'Governance Jobs'],
  ['/admin/policies', 'Policies'],
  ['/five-s', 'Analytics'],
  ['/five-s/explore', 'Explorer'],
  ['/five-s/duplicates', 'Explorer'],
  ['/five-s/access', 'Explorer'],
  ['/five-s/report', 'Explorer'],
  ['/five-s/scanner', 'Inventory'],
  ['/reports', 'Insights & Recommendations'],
  ['/admin/storage-endpoints', 'Storage Endpoints'],
  ['/admin/zones', 'Storage Endpoints'],
  ['/admin/identity', 'Identity & Users'],
  ['/admin/identity-sources', 'Identity & Users'],
  ['/admin/tags', 'Settings'],
  ['/admin/advanced-settings', 'Settings']
];

const matches = (pathname: string, prefix: string): boolean =>
  prefix.endsWith('/')
    ? pathname.startsWith(prefix) && pathname.length > prefix.length
    : pathname === prefix || pathname.startsWith(`${prefix}/`);

export const pageTitle = (pathname: string, alertsCount = 0): string => {
  const match = TITLES.filter(([prefix]) => matches(pathname, prefix)).sort((a, b) => b[0].length - a[0].length)[0];
  const base = match ? `${match[1]} · BornToShare` : 'BornToShare';
  return alertsCount > 0 ? `(${alertsCount}) ${base}` : base;
};
