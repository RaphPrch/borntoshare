declare const process: {
  env: Record<string, string | undefined>;
};

type ServiceKind = 'auth' | 'core';

type DirectRoute = {
  service: ServiceKind;
  path: string;
  internal: boolean;
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
  }
}

// Governance (orchestration) routes are served by core-service under /governance.
function governanceRoute(path: string): DirectRoute {
  return { service: 'core', path: `/governance${path}`, internal: true };
}

function stripApiPrefix(pathname: string): string {
  if (pathname === '/api') return '/';
  if (pathname.startsWith('/api/')) return pathname.slice(4) || '/';
  return pathname.startsWith('/') ? pathname : `/${pathname}`;
}

export function resolveDirectRoute(pathname: string): DirectRoute | null {
  const path = stripApiPrefix(pathname);

  if (path.startsWith('/internal')) {
    return null;
  }

  if (path.startsWith('/auth/')) {
    return { service: 'auth', path, internal: false };
  }

  if (path === '/access-requests/bulk' || /^\/storage-root-access-profiles\/\d+\/adopt$/.test(path)) {
    return governanceRoute(path);
  }

  if (path === '/identity-sources/secret-ref') {
    return { service: 'auth', path: '/internal/identity-sources/secret-ref', internal: true };
  }

  if (path === '/storage-endpoints/secret-ref') {
    return { service: 'auth', path: '/internal/storage-endpoints/secret-ref', internal: true };
  }

  if (path === '/storage-roots/discovery-sync' || path === '/storage-roots/discovery-sync/') {
    return { service: 'core', path: '/storage-roots/discovery-sync', internal: true };
  }

  if (
    /^\/storage-endpoints\/\d+\/probe-result\/?$/.test(path) ||
    /^\/storage-roots\/\d+\/probe-result\/?$/.test(path)
  ) {
    return { service: 'core', path: path.replace(/\/$/, ''), internal: true };
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

    return { service: 'core', path, internal: false };
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
    path.startsWith('/dashboard') ||
    path.startsWith('/naming-policies') ||
    path.startsWith('/governance-alerts') ||
    path.startsWith('/health') ||
    path.startsWith('/storage-endpoints') ||
    path.startsWith('/storage-roots') ||
    path.startsWith('/tags') ||
    path.startsWith('/zones')
  ) {
    return { service: 'core', path, internal: false };
  }

  return null;
}
