const PUBLIC_PATH_PREFIXES = [
  '/login',
  '/logout',
  '/_app',
  '/favicon',
  '/css',
  '/api/auth'
];

const STATIC_PATH_PREFIXES = ['/favicon', '/_app', '/css'];

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATH_PREFIXES.some((p) => pathname.startsWith(p));
}

export function shouldSkipHydration(pathname: string): boolean {
  return STATIC_PATH_PREFIXES.some((p) => pathname.startsWith(p));
}

