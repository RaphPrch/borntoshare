/**
 * Main navigation of the v2 interface: four sections, each item with the paths it covers.
 * The sidebar draws it, the top bar takes its breadcrumb from it (section › page).
 * The menu names are product names (kept in English in both languages, as chosen for v2).
 */
import { t } from '$lib/i18n';

export type NavTab = { href: string; label: string; also?: string[] };
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
    { key: 'workspace', label: 'Workspace', items: [{ href: '/dashboard', label: 'Dashboard', icon: 'bi-grid-1x2', also: ['/live'] }] },
    {
      key: 'governance',
      label: 'Governance',
      items: [
        { href: '/storage-roots', label: 'Storage Roots', icon: 'bi-folder2-open' },
        ...(governance ? [{ href: '/access-requests', label: 'Access Management', icon: 'bi-shield-check', also: ['/exposure'], count: ctx.pending,
            tabs: [{ href: '/access-requests', label: t('Requests') }, ...(ctx.staff ? [{ href: '/exposure', label: t('Exposure') }] : [])] }] : []),
        ...(ctx.staff ? [{ href: '/observability', label: 'Governance Jobs', icon: 'bi-list-task', count: ctx.admin ? ctx.critical : 0, danger: true }] : [])
      ]
    },
    {
      key: 'intelligence',
      label: 'Storage Intelligence',
      items: [
        ...(fives && ctx.staff
          ? [
              { href: '/five-s/explore', label: 'Explorer', icon: 'bi-columns-gap', also: ['/five-s/duplicates'] },
              { href: '/five-s/scanner', label: 'Inventory', icon: 'bi-list-ul' },
              { href: '/five-s', label: 'Analytics', icon: 'bi-bar-chart', also: ['/five-s/report'] }
            ]
          : []),
        ...(ctx.staff ? [{ href: '/reports', label: 'Insights & Recommendations', icon: 'bi-lightbulb', also: ctx.admin ? ['/admin/policies'] : [],
            tabs: [{ href: '/reports', label: t('Reports') }, ...(ctx.admin ? [{ href: '/admin/policies', label: t('Policies') }] : [])] }] : [])
      ]
    },
    {
      key: 'administration',
      label: 'Administration',
      items: ctx.admin
        ? [
            { href: '/admin/storage-endpoints', label: 'Storage Endpoints', icon: 'bi-hdd-stack', also: ['/admin/zones'],
              tabs: [{ href: '/admin/storage-endpoints', label: t('Servers') }, { href: '/admin/zones', label: t('Zones') }] },
            { href: '/admin/advanced-settings/infrastructure', label: 'Workers', icon: 'bi-cpu' },
            { href: '/admin/identity', label: 'Identity & Users', icon: 'bi-people', also: ['/admin/identity-sources'],
              tabs: [{ href: '/admin/identity', label: t('Identities') }, { href: '/admin/identity/admins', label: t('Administrators') }, { href: '/admin/identity-sources', label: t('Directories') }] },
            { href: '/admin/advanced-settings', label: 'Settings', icon: 'bi-sliders', also: ['/admin/tags'],
              tabs: [{ href: '/admin/advanced-settings', label: t('Settings') }, { href: '/admin/tags', label: t('Tags') }] }
          ]
        : []
    }
  ];
  return sections.filter((section) => section.items.length > 0);
}

const covers = (prefix: string, path: string) => path === prefix || path.startsWith(`${prefix}/`);

/** The item of the current page: the longest matching prefix wins (Workers before Settings, Explorer before Analytics). */
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
