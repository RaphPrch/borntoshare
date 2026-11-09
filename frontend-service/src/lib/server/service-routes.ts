declare const process: {
  env: Record<string, string | undefined>;
};

type ServiceKind = 'auth' | 'core' | 'fives';

type DirectRoute = {
  service: ServiceKind;
  path: string;
};

function normalizeBaseUrl(raw: string | undefined): string | null {
  const value = (raw ?? '').trim().replace(/\/$/, '');
  return value || null;
}

export function getServiceBaseUrl(service: ServiceKind): string | null {
  switch (service) {
    case 'auth':
      return normalizeBaseUrl(process.env.B2S_AUTH_URL);
    case 'core':
      return normalizeBaseUrl(process.env.B2S_CORE_URL);
    // Optional module « 5S et hygiène des données » (its own container); it checks its license itself
    case 'fives':
      return normalizeBaseUrl(process.env.B2S_FIVES_URL);
  }
}

// Governance (orchestration) routes are served by core-service under /governance.
function governanceRoute(path: string): DirectRoute {
  return { service: 'core', path: `/governance${path}` };
}

export function stripApiPrefix(pathname: string): string {
  if (pathname === '/api') return '/';
  if (pathname.startsWith('/api/')) return pathname.slice(4) || '/';
  return pathname.startsWith('/') ? pathname : `/${pathname}`;
}

export function resolveDirectRoute(pathname: string): DirectRoute | null {
  const path = stripApiPrefix(pathname);

  if (path.startsWith('/internal') || path.startsWith('/auth/internal')) {
    return null;
  }

  if (path.startsWith('/auth/')) {
    return { service: 'auth', path };
  }

  // /api/modules/fives/x → fives-service /x (never its internal routes)
  if (path === '/modules/fives' || path.startsWith('/modules/fives/')) {
    const rest = path.slice('/modules/fives'.length) || '/';
    return rest.startsWith('/internal') ? null : { service: 'fives', path: rest };
  }

  if (path === '/access-requests/bulk' || /^\/storage-root-access-profiles\/\d+\/adopt$/.test(path)) {
    return governanceRoute(path);
  }

  if (path === '/identity-sources/secret-ref') {
    return { service: 'auth', path: '/internal/identity-sources/secret-ref' };
  }

  if (path === '/storage-endpoints/secret-ref') {
    return { service: 'auth', path: '/internal/storage-endpoints/secret-ref' };
  }

  if (path === '/storage-roots/discovery-sync' || path === '/storage-roots/discovery-sync/') {
    return { service: 'core', path: '/storage-roots/discovery-sync' };
  }

  if (
    /^\/storage-endpoints\/\d+\/probe-result\/?$/.test(path) ||
    /^\/storage-roots\/\d+\/probe-result\/?$/.test(path)
  ) {
    return { service: 'core', path: path.replace(/\/$/, '') };
  }

  if (
    path.startsWith('/identity-sources') ||
    path === '/identity' ||
    path.startsWith('/identity/')
  ) {
    if (path === '/identity' || path.startsWith('/identity/')) {
      const governanceIdentityPaths = [
        '/identity/search',
        '/identity/import',
        '/identity/snapshots',
        '/identity/jobs',
        '/identity/discover'
      ];
      if (governanceIdentityPaths.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))) {
        return governanceRoute(path);
      }
    }

    return { service: 'core', path };
  }

  if (path.startsWith('/admin/jobs') || path.startsWith('/probes')) {
    return governanceRoute(path);
  }

  if (
    path.startsWith('/access-profiles') ||
    path.startsWith('/access-requests') ||
    path.startsWith('/activity') ||
    path.startsWith('/admin/advanced-settings') ||
    path.startsWith('/admin/config') ||
    path.startsWith('/admin/network') ||
    path.startsWith('/admin/setup') ||
    path.startsWith('/dashboard') ||
    path.startsWith('/naming-policies') ||
    path.startsWith('/governance-alerts') ||
    path.startsWith('/health') ||
    path.startsWith('/infrastructure') ||
    path.startsWith('/observability') ||
    path.startsWith('/storage-endpoints') ||
    path.startsWith('/storage-roots') ||
    path.startsWith('/tags') ||
    path.startsWith('/extensions') ||
    path.startsWith('/policies') ||
    path.startsWith('/quota-requests') ||
    path.startsWith('/insights') ||
    path.startsWith('/features') ||
    path.startsWith('/zones')
  ) {
    return { service: 'core', path };
  }

  return null;
}
