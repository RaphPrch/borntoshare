// Who may open which page of the app (the layout redirects, the menu hides the same entries): one place for the rules.
// The data stays protected by core-service whatever this says; this only spares a page that would answer « forbidden ».

export type AccessContext = { admin: boolean; staff: boolean; features: string[] };

const covers = (prefix: string, path: string) => path === prefix || path.startsWith(`${prefix}/`);

/** The screens about the folders: administrators and guardians (a user has his requests and his folders) */
export const STAFF_ONLY = ['/observability', '/reports', '/five-s', '/exposure', '/access-explorer', '/assistant', '/pilot', '/access-reviews'];
/** Audit exports of the whole platform */
export const ADMIN_ONLY = ['/evidence'];

/** Where to send someone who may not open `path`; null when the page is his */
export function redirectFor(path: string, ctx: AccessContext): string | null {
  if (!ctx.staff && STAFF_ONLY.some((prefix) => covers(prefix, path))) return '/dashboard';
  if (!ctx.admin && ADMIN_ONLY.some((prefix) => covers(prefix, path))) return '/dashboard';
  // An installation for the 5S only: no access request, no exposure; the dashboard of a guardian is the 5S
  if (!ctx.features.includes('governance')) {
    const home = ctx.features.includes('fives') && ctx.staff ? '/five-s' : '/dashboard';
    if (covers('/access-requests', path) || covers('/exposure', path) || covers('/access-explorer', path) || (path === '/dashboard' && ctx.staff && !ctx.admin)) {
      return path === home ? null : home;
    }
  }
  return null;
}
