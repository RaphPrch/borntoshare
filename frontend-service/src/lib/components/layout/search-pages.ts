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
    { title: 'Assistant', description: 'Questions on the folders, answered as lists to export.', href: '/assistant', icon: 'bi-chat-square-text' },
    { title: 'Access Explorer', description: 'What a user or a group reaches, and why (Access Management › Explorer).', href: '/access-explorer', icon: 'bi-diagram-3' },
    { title: 'Exposure map', description: 'Map of the folders by how widely their permissions open them.', href: '/insights/exposure', icon: 'bi-globe2' },
    { title: 'Insights & Recommendations', description: 'The state of the data: coverage, alerts, availability, and what to handle.', href: '/insights', icon: 'bi-lightbulb' },
    { title: 'Recommendations', description: 'What the measures, scans and ACL reads reveal, with the folders concerned.', href: '/insights/recommendations', icon: 'bi-lightbulb' },
    { title: 'Reports', description: 'Storage, security, access and 5S reports to print or save as PDF.', href: '/reports', icon: 'bi-printer' }
  ],
  admin: [
    { title: 'Storage Endpoints', description: 'Configure and manage storage endpoint connectors.', href: '/admin/storage-endpoints', icon: 'bi-hdd-network' },
    { title: 'Zones', description: 'Manage sites and zones topology.', href: '/admin/zones', icon: 'bi-diagram-2' },
    { title: 'Storage Topology', description: 'Map of the storage: zones, servers, volumes, shares, DFS and folders, with their state.', href: '/insights/topology', icon: 'bi-diagram-2' },
    { title: 'Policies', description: 'Smart policies: tag, alert and notify when folders match a condition.', href: '/policies', icon: 'bi-magic' },
    { title: 'Identity & Users', description: 'Manage local accounts and directory users or groups.', href: '/admin/identity', icon: 'bi-people' },
    { title: 'Tags', description: 'Define and manage governance tags.', href: '/admin/tags', icon: 'bi-tags' },
    { title: 'Identity Sources', description: 'Manage LDAP/OIDC identity providers and sync sources.', href: '/admin/identity-sources', icon: 'bi-diagram-3' },
    { title: 'Settings', description: 'Naming, governance, security, network, infrastructure, license and integrations.', href: '/admin/advanced-settings', icon: 'bi-sliders' },
    { title: 'Evidence Center', description: 'Audit evidence packs, review campaign exports and printable reports.', href: '/evidence', icon: 'bi-file-earmark-zip' }
  ]
};

export default searchPages;
