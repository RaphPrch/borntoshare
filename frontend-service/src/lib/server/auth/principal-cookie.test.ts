import {
  clearAuthCookiesWithNames,
  isPrincipalExpired,
  issuePrincipalCookieFromMe,
  parsePrincipalCookie,
  principalToMe,
  verifyPrincipalCookieWithKey
} from './principal-cookie';

declare const process: { exitCode?: number };

type CookieOp = { type: 'delete'; name: string; path?: string };

const makeCookies = () => {
  const ops: CookieOp[] = [];
  return {
    api: {
      delete(name: string, opts?: { path?: string }) {
        ops.push({ type: 'delete', name, path: opts?.path });
      }
    },
    ops
  };
};

async function testIssueVerifyRoundtrip() {
  const token = await issuePrincipalCookieFromMe(
    {
      id: 42,
      username: 'alice',
      display_name: 'Alice',
      email: 'alice@example.org',
      roles: ['platform_admin'],
      is_admin: true
    },
    900,
    'k1'
  );

  const verified = await verifyPrincipalCookieWithKey(token, 'k1');
  if (!verified) {
    throw new Error('verify should succeed with valid signature');
  }
  if (verified.id !== 42 || verified.username !== 'alice') {
    throw new Error('unexpected principal payload after verify');
  }
}

async function testVerifyRejectsTampered() {
  const token = await issuePrincipalCookieFromMe(
    {
      id: 1,
      username: 'u1',
      display_name: null,
      email: null,
      roles: ['user'],
      is_admin: false
    },
    900,
    'k2'
  );

  const [payload, sig] = token.split('.');
  const tampered = `${payload}x.${sig}`;
  const verified = await verifyPrincipalCookieWithKey(tampered, 'k2');
  if (verified !== null) {
    throw new Error('tampered signature should be rejected');
  }
}

function testParseAndExpiryAndTransform() {
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    id: 9,
    username: 'u9',
    display_name: 'U9',
    email: null,
    roles: ['user'],
    is_admin: false,
    ver: 1,
    exp: now + 60
  };
  const payloadB64 = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
  const parsed = parsePrincipalCookie(`${payloadB64}.invalid`);
  if (!parsed) {
    throw new Error('parse should decode payload even with invalid signature');
  }
  if (isPrincipalExpired(parsed)) {
    throw new Error('payload should not be expired');
  }

  const me = principalToMe(parsed);
  if (me.id !== 9 || me.username !== 'u9') {
    throw new Error('principalToMe mapping failed');
  }
}

function testClearCookies() {
  const { api, ops } = makeCookies();
  clearAuthCookiesWithNames(api as any, {
    sessionCookieName: 'b2s_session',
    principalCookieName: 'b2s_principal'
  });
  if (ops.length !== 2) {
    throw new Error('clearAuthCookiesWithNames should delete both cookies');
  }
}

async function run() {
  await testIssueVerifyRoundtrip();
  await testVerifyRejectsTampered();
  testParseAndExpiryAndTransform();
  testClearCookies();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
