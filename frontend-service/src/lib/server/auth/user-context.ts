import type { RequestEvent } from '@sveltejs/kit';

import { unwrapDataStrict } from '../../api/http/envelopes';
import { normalizeMe, type Me } from '../../types/me';
import { getServiceBaseUrl } from '../service-routes';
import {
  clearAuthCookiesWithNames,
  isPrincipalExpired,
  issuePrincipalCookieFromMe,
  principalToMe,
  verifyPrincipalCookieWithKey
} from './principal-cookie';

declare const process: {
  env: Record<string, string | undefined>;
};

const env = process.env;

const SESSION_COOKIE_NAME = env.SESSION_COOKIE_NAME ?? 'b2s_session';
const PRINCIPAL_COOKIE_NAME = env.PRINCIPAL_COOKIE_NAME ?? 'b2s_principal';

const PRINCIPAL_TTL_SECONDS = Number.parseInt(
  env.PRINCIPAL_TTL_SECONDS ?? '900',
  10
);

const PRINCIPAL_COOKIE_SAMESITE = (() => {
  const value = (env.PRINCIPAL_COOKIE_SAMESITE ?? 'lax').toLowerCase();
  if (value === 'none' || value === 'strict' || value === 'lax') {
    return value;
  }
  return 'lax';
})();

// Secure by default whenever the public origin is HTTPS; explicit env vars still win.
const PRINCIPAL_COOKIE_SECURE =
  (env.PRINCIPAL_COOKIE_SECURE ??
    env.B2S_USE_HTTPS ??
    String((env.ORIGIN ?? '').trim().toLowerCase().startsWith('https://'))) === 'true';

const DEV_PRINCIPAL_SIGNING_KEY = 'dev-principal-key';
const PRINCIPAL_SIGNING_KEY = env.PRINCIPAL_SIGNING_KEY || DEV_PRINCIPAL_SIGNING_KEY;

// The principal cookie carries the user's roles: a publicly known key would let anyone forge an admin.
if ((env.APP_ENV ?? 'dev').trim().toLowerCase() === 'prod' && PRINCIPAL_SIGNING_KEY === DEV_PRINCIPAL_SIGNING_KEY) {
  throw new Error('PRINCIPAL_SIGNING_KEY must be set when APP_ENV=prod');
}

async function hydrateUserFromAuthMe(event: RequestEvent): Promise<Me | null> {
  const authUrl = getServiceBaseUrl('auth');
  if (!authUrl) {
    return null;
  }

  const cookieHeader = event.request.headers.get('cookie') || '';
  const meUrl = `${authUrl}/auth/me`;

  let res: Response;
  try {
    res = await fetch(meUrl, {
      method: 'GET',
      headers: {
        cookie: cookieHeader,
        'x-forwarded-host': event.url.host,
        'x-forwarded-proto': event.url.protocol.replace(':', '')
      }
    });
  } catch {
    return null;
  }

  if (!res.ok) {
    return null;
  }

  let raw: unknown;
  try {
    raw = await res.json();
  } catch {
    return null;
  }

  let payload: unknown;
  try {
      payload = unwrapDataStrict(raw, 'GET /auth/me');
  } catch {
    return null;
  }

  const me = normalizeMe(payload);

  if (!me.id) {
    return null;
  }

  const snapshotCookie = await issuePrincipalCookieFromMe(
    me,
    PRINCIPAL_TTL_SECONDS,
    PRINCIPAL_SIGNING_KEY
  );

  event.cookies.set(PRINCIPAL_COOKIE_NAME, snapshotCookie, {
    path: '/',
    httpOnly: true,
    secure: PRINCIPAL_COOKIE_SECURE,
    sameSite: PRINCIPAL_COOKIE_SAMESITE,
    maxAge: PRINCIPAL_TTL_SECONDS
  });

  return me;
}

export async function hydrateUserContext(event: RequestEvent): Promise<void> {
  const { cookies } = event;
  const locals = event.locals as { me: Me | null };

  const sessionCookie = cookies.get(SESSION_COOKIE_NAME);
  const rawPrincipal = cookies.get(PRINCIPAL_COOKIE_NAME);

  if (!sessionCookie) {
    locals.me = null;
    if (rawPrincipal) {
      clearAuthCookiesWithNames(cookies, {
        sessionCookieName: SESSION_COOKIE_NAME,
        principalCookieName: PRINCIPAL_COOKIE_NAME
      });
    }
    return;
  }

  if (rawPrincipal) {
    let snapshot: Awaited<ReturnType<typeof verifyPrincipalCookieWithKey>> = null;
    try {
      snapshot = await verifyPrincipalCookieWithKey(
        rawPrincipal,
        PRINCIPAL_SIGNING_KEY
      );
    } catch {
      snapshot = null;
    }

    if (snapshot && !isPrincipalExpired(snapshot)) {
      locals.me = principalToMe(snapshot);
      return;
    }
  }

  let hydrated: Me | null = null;
  try {
    hydrated = await hydrateUserFromAuthMe(event);
  } catch {
    hydrated = null;
  }

  if (hydrated) {
    locals.me = hydrated;
    return;
  }

  clearAuthCookiesWithNames(cookies, {
    sessionCookieName: SESSION_COOKIE_NAME,
    principalCookieName: PRINCIPAL_COOKIE_NAME
  });
  locals.me = null;
}
