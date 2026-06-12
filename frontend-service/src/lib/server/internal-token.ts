declare const process: {
  env: Record<string, string | undefined>;
};

const TOKEN_PREFIX = 'v1';

function base64UrlEncode(input: ArrayBuffer): string {
  const bytes = new Uint8Array(input);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function parseKeyring(raw: string | undefined): Array<[string, string]> {
  return (raw ?? '')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part.includes(':'))
    .map((part) => {
      const [kid, ...rest] = part.split(':');
      return [kid.trim(), rest.join(':').trim()] as [string, string];
    })
    .filter(([kid, secret]) => kid.length > 0 && secret.length > 0);
}

async function signInternalToken(kid: string, secret: string, ttlSeconds: number): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + Math.max(1, ttlSeconds);
  const message = `${TOKEN_PREFIX}.${kid}.${exp}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return `${message}.${base64UrlEncode(signature)}`;
}

export async function buildInternalHeaders(): Promise<HeadersInit> {
  const env = process.env;
  const headers: Record<string, string> = {};
  const mode = (env.INTERNAL_TOKEN_MODE ?? 'hmac').trim().toLowerCase();

  if (mode === 'static') {
    const token = (env.INTERNAL_TOKEN ?? '').trim();
    if (token) {
      headers['X-Internal-Token'] = token;
    }
  } else {
    const firstKey = parseKeyring(env.INTERNAL_TOKEN_KEYS)[0];
    if (firstKey) {
      const ttl = Number.parseInt(env.INTERNAL_TOKEN_TTL_SEC ?? '300', 10);
      headers['X-Internal-Token'] = await signInternalToken(firstKey[0], firstKey[1], Number.isFinite(ttl) ? ttl : 300);
    }
  }

  const serviceToken = (env.SERVICE_TOKEN ?? '').trim();
  if (serviceToken) {
    headers['X-Service-Token'] = serviceToken;
  }

  return headers;
}

export async function buildStaticInternalHeaders(): Promise<HeadersInit> {
  const headers: Record<string, string> = {};
  const token = (process.env.INTERNAL_TOKEN ?? '').trim();
  if (token) {
    headers['X-Internal-Token'] = token;
  }

  const serviceToken = (process.env.SERVICE_TOKEN ?? '').trim();
  if (serviceToken) {
    headers['X-Service-Token'] = serviceToken;
  }

  return headers;
}
