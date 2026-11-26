/**
 * Main navigation of the v2 interface: four sections, each item with the paths it covers. Only the entries whose
 * page works are listed (no empty screen): Change Monitoring and Storage Passport wait for their feature.
 * The ☰ menu of the top bar draws it, the context bar takes its breadcrumb and tabs from it (section › page).
 * The menu names are product names (kept in English in both languages, as chosen for v2).
 */
import { t } from '$lib/i18n';

/** `menu: false`: a tab of the context bar that the ☰ menu does not repeat (the entry itself already leads there) */
export type NavTab = { href: string; label: string; also?: string[]; menu?: boolean };
export type NavItem = {
  href: string;
  /** Pages gathered under this entry: underlined tabs under the top bar */
  tabs?: NavTab[];
  label: string;
  icon: string;
  /** Paths (prefixes) that belong to this item, besides its href */
  also?: string[];
  count?: number;
  danger?: boolean;
  /** The main action of the entry: shown at the right of the context bar, at the same place on each of its pages */
  action?: { href: string; label: string; icon: string };
};
export type NavSection = { key: string; label: string; items: NavItem[] };

export type NavContext = {
  admin: boolean;
  /** Administrators and guardians */
  staff: boolean;
  features: string[];
  pending: number;
  critical: number;
};

export function buildNav(ctx: NavContext): NavSection[] {
  const governance = ctx.features.includes('governance');
  const fives = ctx.features.includes('fives');
  const sections: NavSection[] = [
    { key: 'workspace', label: 'Workspace', items: [
      { href: '/dashboard', label: 'Dashboard', icon: 'bi-grid-1x2', also: ['/live'] },
      // Questions on the folders, answered as lists to export (administrators and guardians); /pilot redirects here
      ...(ctx.staff ? [{ href: '/assistant', label: 'Assistant', icon: 'bi-chat-square-text', also: ['/pilot'] }] : []),
      // What waits for this person: requests to decide, reviews, alerts, recommendations, their own requests
      { href: '/tasks', label: 'My Tasks', icon: 'bi-check2-square' }
    ] },
    {
      key: 'governance',
      label: 'Governance',
      items: [
        // Adding folders: the « + » of the folder list (no button in the top bar)
        { href: '/storage-roots', label: 'Storage Roots', icon: 'bi-folder2-open' },
        ...(governance ? [{ href: '/access-requests', label: 'Access Management', icon: 'bi-shield-check', also: ['/access-reviews'], count: ctx.pending,
            tabs: [{ href: '/access-requests', label: t('Requests'), menu: false },
              ...(ctx.staff ? [{ href: '/access-reviews', label: t('Reviews') }] : [])] }] : []),
        // Who reaches what: the map of the folders by how widely their last ACL read opens them
        ...(governance && ctx.staff ? [{ href: '/access-explorer', label: 'Access Explorer', icon: 'bi-diagram-3', also: ['/exposure'] }] : []),
        // Administrators: the platform (health, alerts, jobs) and, as a tab, what a manager sees; managers: their own view
        ...(ctx.admin
          ? [{ href: '/observability', label: 'Governance Jobs', icon: 'bi-list-task', count: ctx.critical, danger: true,
              tabs: [{ href: '/observability', label: t('Administrator view') }, { href: '/observability/mine', label: t('Manager view') }] }]
          : ctx.staff ? [{ href: '/observability/mine', label: 'Governance Jobs', icon: 'bi-list-task' }] : []),
        // Automations of the governance (tags, alerts, scans… on a rule): administrators
        ...(ctx.admin ? [{ href: '/policies', label: 'Policies', icon: 'bi-magic' }] : [])
      ]
    },
    {
      key: 'intelligence',
      label: 'Storage Intelligence',
      // The 5S module (licensed and switched on) brings Explorer, Inventory and Analytics; the recommendations and
      // the audit evidence come from the governance and stay without it
      items: ctx.staff
        ? [
            ...(fives
              ? [
                  // Every page of one folder (content, 5S workshop, duplicates, rights to review, report) belongs to Explorer
                  { href: '/five-s/explore', label: 'Explorer', icon: 'bi-columns-gap', also: ['/five-s/duplicates', '/five-s/access', '/five-s/report'] },
                  { href: '/five-s/scanner', label: 'Inventory', icon: 'bi-list-ul' },
                  { href: '/five-s', label: 'Analytics', icon: 'bi-bar-chart' }
                ]
              : []),
            { href: '/reports', label: 'Insights & Recommendations', icon: 'bi-lightbulb' },
            // Audit evidence of the whole platform (administrators)
            ...(ctx.admin ? [{ href: '/evidence', label: 'Evidence Center', icon: 'bi-file-earmark-zip' }] : [])
          ]
        : []
    },
    {
      key: 'administration',
      label: 'Administration',
      items: ctx.admin
        ? [
            // The servers, and as a tab the map of the storage: zone → server → volume → share → folder, DFS
            { href: '/admin/storage-endpoints', label: 'Storage Endpoints', icon: 'bi-hdd-stack', also: ['/admin/storage-topology'],
              action: { href: '/admin/storage-endpoints/new', label: t('Add a server'), icon: 'bi-plus-lg' },
              tabs: [{ href: '/admin/storage-endpoints', label: t('Servers'), menu: false }, { href: '/admin/storage-topology', label: t('Topology') }] },
            // Zones: an entry of their own (no longer a tab of the servers)
            { href: '/admin/zones', label: 'Zones', icon: 'bi-geo-alt',
              action: { href: '/admin/zones/new', label: t('Add a zone'), icon: 'bi-plus-lg' } },
            { href: '/admin/identity', label: 'Identity & Users', icon: 'bi-people', also: ['/admin/identity-sources'],
              tabs: [{ href: '/admin/identity', label: t('Identities'), menu: false }, { href: '/admin/identity-sources', label: t('Directories') }] },
            { href: '/admin/advanced-settings', label: 'Settings', icon: 'bi-sliders', also: ['/admin/tags'],
              tabs: [{ href: '/admin/advanced-settings', label: t('Settings'), menu: false }, { href: '/admin/tags', label: t('Tags') }] }
          ]
        : []
    }
  ];
  return sections.filter((section) => section.items.length > 0);
}

const covers = (prefix: string, path: string) => path === prefix || path.startsWith(`${prefix}/`);

/** The item of the current page: the longest matching prefix wins (Explorer before Analytics). */
export function activeItem(sections: NavSection[], path: string): { section: NavSection; item: NavItem } | null {
  let best: { section: NavSection; item: NavItem; length: number } | null = null;
  for (const section of sections) {
    for (const item of section.items) {
      for (const prefix of [item.href, ...(item.also ?? [])]) {
        if (covers(prefix, path) && (!best || prefix.length > best.length)) best = { section, item, length: prefix.length };
      }
    }
  }
  return best ? { section: best.section, item: best.item } : null;
}
