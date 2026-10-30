type SearchPage = {
  title: string;
  description: string;
  href: string;
  icon?: string;
};

// Pages offered by the global search
type SearchPageGroup = 'storageRoots' | 'admin';

const searchPages: Record<SearchPageGroup, SearchPage[]> = {
  storageRoots: [
    {
      title: 'Storage Roots',
      description: 'Browse and manage storage roots.',
      href: '/storage-roots',
      icon: 'bi-hdd-stack'
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

export default searchPages;
