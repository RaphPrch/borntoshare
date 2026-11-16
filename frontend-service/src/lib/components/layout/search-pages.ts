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
    { title: 'Storage Roots', description: 'Browse and manage storage roots.', href: '/storage-roots', icon: 'bi-folder2-open' },
    { title: 'Explorer', description: 'Content of the measured folders, 5S workshop, duplicates, rights to review.', href: '/five-s/explore', icon: 'bi-columns-gap' },
    { title: 'Inventory', description: 'Scans, folders measured, quarantine and archives.', href: '/five-s/scanner', icon: 'bi-list-ul' },
    { title: 'Analytics', description: '5S score of the folders and what to do first.', href: '/five-s', icon: 'bi-bar-chart' },
    { title: 'Pilot', description: 'Questions on the folders, answered as lists to export.', href: '/pilot', icon: 'bi-chat-square-text' }
  ],
  admin: [
    { title: 'Storage Endpoints', description: 'Configure and manage storage endpoint connectors.', href: '/admin/storage-endpoints', icon: 'bi-hdd-network' },
    { title: 'Zones', description: 'Manage sites and zones topology.', href: '/admin/zones', icon: 'bi-diagram-2' },
    { title: 'Policies', description: 'Smart policies: tag, alert and notify when folders match a condition.', href: '/admin/policies', icon: 'bi-magic' },
    { title: 'Identity & Users', description: 'Manage local accounts and directory users or groups.', href: '/admin/identity', icon: 'bi-people' },
    { title: 'Tags', description: 'Define and manage governance tags.', href: '/admin/tags', icon: 'bi-tags' },
    { title: 'Identity Sources', description: 'Manage LDAP/OIDC identity providers and sync sources.', href: '/admin/identity-sources', icon: 'bi-diagram-3' },
    { title: 'Settings', description: 'Naming, governance, security, network, infrastructure, license and integrations.', href: '/admin/advanced-settings', icon: 'bi-sliders' }
  ]
};

export default searchPages;
