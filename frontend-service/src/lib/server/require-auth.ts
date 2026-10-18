import { redirect } from '@sveltejs/kit';
import type { RequestEvent } from '@sveltejs/kit';
import type { Me } from '../types/me';

/**
 * AUTHENTICATION guard (SSR)
 *
 * - Ensures the user is logged in
 * - Returns the authenticated user (Me)
 * - DOES NOT check admin / roles / permissions
 */
export async function requireAuth(event: RequestEvent): Promise<Me> {
  const locals = event.locals as { me?: Me | null };
  const me = locals.me ?? undefined;

  if (!me) {
    const wanted = `${event.url.pathname}${event.url.search}`;
    throw redirect(302, `/login?redirect=${encodeURIComponent(wanted)}`);
  }

  return me;
}
