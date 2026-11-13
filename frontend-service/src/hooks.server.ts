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
 * - CSRF checked by SvelteKit against ORIGIN
 * - Direct backend service routing
 */

import { LOCALE_COOKIE, isLocale, localeFromAcceptLanguage, type Locale } from './lib/i18n';
import type { Handle } from '@sveltejs/kit';
import { redirect } from '@sveltejs/kit';
import { isPublicPath, shouldSkipHydration } from './lib/server/routing/public-paths';
import { proxyApi } from './lib/server/bff/proxy';
import { hydrateUserContext } from './lib/server/auth/user-context';
import { logError } from './lib/logging';

declare const process: {
  env: Record<string, string | undefined>;
  on?: (event: 'unhandledRejection', listener: (reason: unknown) => void) => void;
};

// Node exits on an unhandled rejection: one failed background call (e.g. a fetch started
// during SSR) would take the whole frontend down for every user. Log it instead.
process.on?.('unhandledRejection', (reason) => {
  logError('Unhandled promise rejection', {
    reason: reason instanceof Error ? reason.message : String(reason)
  });
});

/* ============================================================
 * MAIN HANDLE
 * ============================================================ */

// Headers of every answer (pages, API, files): no frame, no type guessing, no referrer outside, no device API;
// HSTS once the public address is HTTPS (FRONTEND_PUBLIC_ORIGIN)
const SECURITY_HEADERS: Record<string, string> = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Cross-Origin-Opener-Policy': 'same-origin',
  ...(String(process.env.ORIGIN ?? '').startsWith('https://') ? { 'Strict-Transport-Security': 'max-age=31536000; includeSubDomains' } : {})
};

function withSecurityHeaders(response: Response): Response {
  try {
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) if (!response.headers.has(name)) response.headers.set(name, value);
    return response;
  } catch {
    // Headers of a proxied answer can be read-only: copy the answer
    const copy = new Response(response.body, response);
    for (const [name, value] of Object.entries(SECURITY_HEADERS)) if (!copy.headers.has(name)) copy.headers.set(name, value);
    return copy;
  }
}

export const handle: Handle = async (input) => withSecurityHeaders(await handleRequest(input));

const handleRequest: Handle = async ({ event, resolve }) => {
  const { url } = event;
  const locals = event.locals as { me: { id?: string | number | null } | null; locale: Locale };

  // Interface language: explicit choice (cookie) first, then the browser preference
  const cookieLocale = event.cookies.get(LOCALE_COOKIE);
  locals.locale = isLocale(cookieLocale)
    ? cookieLocale
    : localeFromAcceptLanguage(event.request.headers.get('accept-language'));
  // Display density chosen by the person (cookie, set by the rail): applied before the first paint, no flash
  const density = event.cookies.get('b2s_density') === 'compact' ? 'compact' : 'comfortable';
  const setHtmlLang = ({ html }: { html: string }) =>
    html.replace('<html lang="fr">', `<html lang="${locals.locale}" data-density="${density}">`);

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
      transformPageChunk: setHtmlLang,
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
      transformPageChunk: setHtmlLang,
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
    transformPageChunk: setHtmlLang,
    filterSerializedResponseHeaders: (name) =>
      name === 'content-type' || name === 'set-cookie'
  });
};
