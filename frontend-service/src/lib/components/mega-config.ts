export type MegaMenuItem = {
  title: string;
  description: string;
  href: string;
  icon?: string;
};

export type MegaMenuConfig = Record<string, MegaMenuItem[]>;

// Single source of truth for the mega-menu keys
// (Topbar + MegaMenu must stay aligned)
export type MegaMenuKey = 'storageRoots' | 'observability' | 'admin';

const megaConfig: Record<MegaMenuKey, MegaMenuItem[]> = {
  storageRoots: [
    {
      title: 'Storage Roots',
      description: 'Browse and manage storage roots.',
      href: '/storage-roots',
      icon: 'bi-hdd-stack'
    }
  ],
  observability: [
    {
      title: 'Events',
      description: 'List all platform actions with severity, time, module and message.',
      href: '/admin/observability/events',
      icon: 'bi-list-ul'
    },
    {
      title: 'Jobs',
      description: 'Observe provisioning jobs, detect stale queued runs and cancel safely.',
      href: '/admin/observability/jobs',
      icon: 'bi-activity'
    }
  ],
  admin: [
    {
      title: 'Storage Endpoints',
      description: 'Configure and manage storage endpoint connectors.',
      href: '/admin/storage-endpoints',
      icon: 'bi-hdd-network'
    },
    {
      title: 'Zones',
      description: 'Manage sites and zones topology.',
      href: '/admin/zones',
      icon: 'bi-diagram-2'
    },
    {
      title: 'Tags',
      description: 'Define and manage governance tags.',
      href: '/admin/tags',
      icon: 'bi-tags'
    },
    {
      title: 'Identity',
      description: 'Manage local accounts and directory users or groups.',
      href: '/admin/identity',
      icon: 'bi-people'
    },
    {
      title: 'Identity Sources',
      description: 'Manage LDAP/OIDC identity providers and sync sources.',
      href: '/admin/identity-sources',
      icon: 'bi-diagram-3'
    },
    {
      title: 'Advanced Settings',
      description: 'Open platform-level security and maintenance settings.',
      href: '/admin/advanced-settings',
      icon: 'bi-sliders'
    }
  ]
};

export default megaConfig;
