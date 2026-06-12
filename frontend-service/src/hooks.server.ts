/**
 * hooks.server.ts — BFF
 *
 * Responsibilities:
 * - Proxy /api/* directly to backend services
 * - Enforce authentication via cookie-session
 * - Hydrate event.locals.me
 * - Handle SvelteKit internal requests safely
 *
 * Assumptions:
 * - HTTP only
 * - Cookie-based session
 * - CSRF disabled
 * - Direct backend service routing
 */

import type { Handle } from '@sveltejs/kit';
import { redirect } from '@sveltejs/kit';
import { isPublicPath, shouldSkipHydration } from './lib/server/routing/public-paths';
import { proxyApi } from './lib/server/bff/proxy';
import { hydrateUserContext } from './lib/server/auth/user-context';
import { logError } from './lib/core/logging';

declare const process: {
  env: Record<string, string | undefined>;
};

const env = process.env;

/* ============================================================
 * MAIN HANDLE
 * ============================================================ */

export const handle: Handle = async ({ event, resolve }) => {
  const { url } = event;
  const locals = event.locals as { me: { id?: string | number | null } | null };

  const tryHydrateUserContext = async () => {
    try {
      await hydrateUserContext(event);
    } catch (error: unknown) {
      logError('SSR hydration failed', {
        route: url.pathname,
        phase: 'hydrateUserContext',
        error: error instanceof Error ? error.message : String(error)
      });
      locals.me = null;
    }
  };

  /* ======================================================
   * 1️⃣ API proxy (BFF)
   * ====================================================== */
  if (url.pathname.startsWith('/api/')) {
    if (!shouldSkipHydration(url.pathname) && !url.pathname.startsWith('/api/auth/')) {
      await tryHydrateUserContext();
    }
    return proxyApi(event);
  }

  /* ======================================================
   * 1.5️⃣ Static/public assets: no session hydration
   * Avoids N calls to /api/auth/me during a single page load.
   * ====================================================== */
  if (shouldSkipHydration(url.pathname)) {
    locals.me = null;
    return resolve(event, {
      filterSerializedResponseHeaders: (name) =>
        name === 'content-type' || name === 'set-cookie'
    });
  }

  /* ======================================================
   * 2️⃣ SESSION HYDRATION (ALWAYS TRY)
   * ====================================================== */

  await tryHydrateUserContext();

  /* ======================================================
   * 3️⃣ Public routes (AFTER hydration)
   * ====================================================== */
  if (isPublicPath(url.pathname)) {
    return resolve(event, {
      filterSerializedResponseHeaders: (name) =>
        name === 'content-type' || name === 'set-cookie'
    });
  }

  /* ======================================================
   * 4️⃣ Private routes require auth
   * ====================================================== */
  if (!locals.me?.id) {
    const wanted = `${url.pathname}${url.search}`;
    throw redirect(
      303,
      `/login?redirect=${encodeURIComponent(wanted)}`
    );
  }

  /* ======================================================
   * 5️⃣ Continue SSR
   * ====================================================== */
  return resolve(event, {
    filterSerializedResponseHeaders: (name) =>
      name === 'content-type' || name === 'set-cookie'
  });
};
