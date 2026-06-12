declare const process: {
  env: Record<string, string | undefined>;
  exitCode?: number;
};

type CookieState = Record<string, string>;

function toCookieHeader(state: CookieState): string {
  return Object.entries(state)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');
}

function createCookies(initial: CookieState) {
  const store: CookieState = { ...initial };
  return {
    api: {
      get(name: string) {
        return store[name] ?? undefined;
      },
      set(name: string, value: string) {
        store[name] = value;
      },
      delete(name: string) {
        delete store[name];
      },
      getAll() {
        return Object.entries(store).map(([name, value]) => ({ name, value }));
      }
    },
    snapshot() {
      return { ...store };
    }
  };
}

function assert(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

async function createHandleDeps() {
  process.env.SESSION_COOKIE_NAME = 'b2s_session';
  process.env.PRINCIPAL_COOKIE_NAME = 'b2s_principal';
  process.env.PRINCIPAL_SIGNING_KEY = 'hooks-test-key';
  process.env.PRINCIPAL_TTL_SECONDS = '900';
  process.env.PRINCIPAL_COOKIE_SAMESITE = 'lax';
  process.env.PRINCIPAL_COOKIE_SECURE = 'false';
  process.env.B2S_AUTH_URL = 'http://auth-service:8000';
  process.env.B2S_DAL_URL = 'http://dal-service:8000/api';
  process.env.B2S_USE_HTTPS = 'false';

  const hooksModule = await import('./hooks.server');
  const principalModule = await import('./lib/server/auth/principal-cookie');

  return {
    handle: hooksModule.handle,
    issuePrincipalCookieFromMe: principalModule.issuePrincipalCookieFromMe
  };
}

function createEvent(pathnameWithQuery: string, cookieState: CookieState) {
  const cookies = createCookies(cookieState);
  const url = new URL(`http://frontend.local${pathnameWithQuery}`);

  const request = {
    method: 'GET',
    headers: {
      get(name: string) {
        if (name.toLowerCase() === 'cookie') {
          return toCookieHeader(cookies.snapshot());
        }
        return null;
      }
    }
  };

  const event: any = {
    url,
    request,
    cookies: cookies.api,
    locals: { me: null },
    getClientAddress: () => '127.0.0.1'
  };

  return { event, cookies };
}

async function testValidSnapshotSkipsAuthMe() {
  const { handle, issuePrincipalCookieFromMe } = await createHandleDeps();
  const principal = await issuePrincipalCookieFromMe(
    {
      id: 101,
      username: 'u101',
      display_name: 'U 101',
      email: 'u101@example.org',
      roles: ['platform_admin'],
      is_admin: true
    },
    900,
    'hooks-test-key'
  );

  const { event } = createEvent('/dashboard', {
    b2s_session: 'sid-101',
    b2s_principal: principal
  });

  let authMeCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (String(input).includes('/auth/me')) {
      authMeCalls += 1;
    }
    return new Response('{}', { status: 500, headers: { 'content-type': 'application/json' } });
  }) as any;

  await handle({
    event,
    resolve: async () => new Response('ok')
  } as any);

  globalThis.fetch = originalFetch;

  assert(authMeCalls === 0, 'valid principal snapshot should skip /auth/me');
  assert(event.locals.me?.id === 101, 'locals.me should be hydrated from principal snapshot');
}

async function testAbsentSnapshotFallsBackToAuthMe() {
  const { handle } = await createHandleDeps();
  const { event } = createEvent('/dashboard', {
    b2s_session: 'sid-201'
  });

  let authMeCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (String(input).includes('/auth/me')) {
      authMeCalls += 1;
      return new Response(
        JSON.stringify({
          ok: true,
          data: {
            identity_id: 201,
            username: 'u201',
            display_name: 'U 201',
            email: 'u201@example.org',
            roles: ['user'],
            is_admin: false
          },
          meta: {},
          error: null
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    return new Response('{}', { status: 500 });
  }) as any;

  await handle({ event, resolve: async () => new Response('ok') } as any);
  globalThis.fetch = originalFetch;

  assert(authMeCalls === 1, 'missing principal snapshot should call /auth/me once');
  assert(event.locals.me?.id === 201, 'locals.me should be hydrated from fallback /auth/me');
}

async function testExpiredSnapshotFallsBackToAuthMe() {
  const { handle, issuePrincipalCookieFromMe } = await createHandleDeps();
  const principal = await issuePrincipalCookieFromMe(
    {
      id: 301,
      username: 'u301',
      display_name: null,
      email: null,
      roles: ['user'],
      is_admin: false
    },
    1,
    'hooks-test-key'
  );

  const { event } = createEvent('/dashboard', {
    b2s_session: 'sid-301',
    b2s_principal: principal
  });

  const originalNow = Date.now;
  Date.now = () => originalNow() + 120_000;

  let authMeCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (String(input).includes('/auth/me')) {
      authMeCalls += 1;
      return new Response(
        JSON.stringify({
          ok: true,
          data: {
            identity_id: 301,
            username: 'u301',
            display_name: null,
            email: null,
            roles: ['user'],
            is_admin: false
          },
          meta: {},
          error: null
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    return new Response('{}', { status: 500 });
  }) as any;

  await handle({ event, resolve: async () => new Response('ok') } as any);

  Date.now = originalNow;
  globalThis.fetch = originalFetch;

  assert(authMeCalls === 1, 'expired principal snapshot should fallback to /auth/me');
}

async function testInvalidSnapshotFallsBackToAuthMe() {
  const { handle, issuePrincipalCookieFromMe } = await createHandleDeps();
  const principal = await issuePrincipalCookieFromMe(
    {
      id: 401,
      username: 'u401',
      display_name: null,
      email: null,
      roles: ['user'],
      is_admin: false
    },
    900,
    'hooks-test-key'
  );

  const [payload, sig] = principal.split('.');
  const invalidPrincipal = `${payload}x.${sig}`;

  const { event } = createEvent('/dashboard', {
    b2s_session: 'sid-401',
    b2s_principal: invalidPrincipal
  });

  let authMeCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (String(input).includes('/auth/me')) {
      authMeCalls += 1;
      return new Response(
        JSON.stringify({
          ok: true,
          data: {
            identity_id: 401,
            username: 'u401',
            display_name: null,
            email: null,
            roles: ['user'],
            is_admin: false
          },
          meta: {},
          error: null
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    return new Response('{}', { status: 500 });
  }) as any;

  await handle({ event, resolve: async () => new Response('ok') } as any);
  globalThis.fetch = originalFetch;

  assert(authMeCalls === 1, 'invalid principal snapshot should fallback to /auth/me');
}

async function testUnauthenticatedRedirectKeepsQueryString() {
  const { handle } = await createHandleDeps();
  const { event } = createEvent('/access-requests?status=pending&root=12', {});

  let redirectedTo = '';
  try {
    await handle({ event, resolve: async () => new Response('ok') } as any);
  } catch (e: any) {
    redirectedTo = String(e?.location ?? '');
  }

  assert(
    redirectedTo === '/login?redirect=%2Faccess-requests%3Fstatus%3Dpending%26root%3D12',
    'unauthenticated redirect should keep pathname and query string'
  );
}

async function testApiProxyHydratesPrincipalBeforeForwarding() {
  const { handle, issuePrincipalCookieFromMe } = await createHandleDeps();
  const principal = await issuePrincipalCookieFromMe(
    {
      id: 501,
      username: 'admin',
      display_name: 'Admin',
      email: 'admin@example.org',
      roles: ['platform_admin'],
      is_admin: true
    },
    900,
    'hooks-test-key'
  );

  const { event } = createEvent('/api/dashboard/platform-overview', {
    b2s_session: 'sid-501',
    b2s_principal: principal
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    return new Response(
      JSON.stringify({
        ok: true,
        roles: headers.get('x-roles') ?? '',
        identity: headers.get('x-identity-id') ?? ''
      }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    );
  }) as any;

  const response = await handle({
    event,
    resolve: async () => new Response('ok')
  } as any);

  globalThis.fetch = originalFetch;

  const payload = await response.json();
  assert(String(payload?.roles).includes('platform_admin'), 'api proxy should forward hydrated roles');
  assert(String(payload?.identity) === '501', 'api proxy should forward hydrated identity id');
}

async function run() {
  await testValidSnapshotSkipsAuthMe();
  await testAbsentSnapshotFallsBackToAuthMe();
  await testExpiredSnapshotFallsBackToAuthMe();
  await testInvalidSnapshotFallsBackToAuthMe();
  await testUnauthenticatedRedirectKeepsQueryString();
  await testApiProxyHydratesPrincipalBeforeForwarding();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
