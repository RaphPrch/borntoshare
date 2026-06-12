import type { Cookies } from '@sveltejs/kit';
import type { Me } from '../../types/me';
import type { PrincipalSnapshot } from './principal-types';

const DEFAULT_SIGNING_KEY = 'dev-principal-key';
const DEFAULT_SESSION_COOKIE_NAME = 'b2s_session';
const DEFAULT_PRINCIPAL_COOKIE_NAME = 'b2s_principal';

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

const signingKeyPromises = new Map<string, Promise<CryptoKey>>();

type AuthCookieNames = {
  sessionCookieName?: string;
  principalCookieName?: string;
};

function getSigningKey(signingKey: string): Promise<CryptoKey> {
  const cached = signingKeyPromises.get(signingKey);
  if (cached) {
    return cached;
  }

  const created = crypto.subtle.importKey(
      'raw',
      textEncoder.encode(signingKey),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign', 'verify']
    );

  signingKeyPromises.set(signingKey, created);

  return created;
}

function bytesToBase64(input: Uint8Array): string {
  let binary = '';
  for (const byte of input) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function base64ToBytes(input: string): Uint8Array {
  const binary = atob(input);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

function toArrayBuffer(input: Uint8Array): ArrayBuffer {
  return input.buffer.slice(
    input.byteOffset,
    input.byteOffset + input.byteLength
  ) as ArrayBuffer;
}

function toBase64Url(base64: string): string {
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function fromBase64Url(input: string): string {
  let base64 = input.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4 !== 0) {
    base64 += '=';
  }
  return base64;
}

function base64UrlEncode(input: string): string {
  return toBase64Url(bytesToBase64(textEncoder.encode(input)));
}

function base64UrlDecode(input: string): string {
  return textDecoder.decode(base64ToBytes(fromBase64Url(input)));
}

async function sign(payloadB64: string, signingKey: string): Promise<string> {
  const key = await getSigningKey(signingKey);
  const signature = await crypto.subtle.sign('HMAC', key, textEncoder.encode(payloadB64));
  return toBase64Url(bytesToBase64(new Uint8Array(signature)));
}

async function verifySignature(
  payloadB64: string,
  signature: string,
  signingKey: string
): Promise<boolean> {
  const key = await getSigningKey(signingKey);
  try {
    return await crypto.subtle.verify(
      'HMAC',
      key,
      toArrayBuffer(base64ToBytes(fromBase64Url(signature))),
      textEncoder.encode(payloadB64)
    );
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object';
}

function toSnapshot(value: unknown): PrincipalSnapshot | null {
  if (!isRecord(value)) return null;

  const id = Number(value.id);
  const exp = Number(value.exp);
  const ver = Number(value.ver);
  const username = String(value.username ?? '').trim();
  const roles = Array.isArray(value.roles)
    ? value.roles.map((r) => String(r).trim()).filter(Boolean)
    : [];
  const isAdmin = roles.some((role) => {
    const normalized = role.toLowerCase();
    return normalized === 'platform_admin' || normalized === 'admin';
  });

  if (!Number.isFinite(id) || id <= 0) return null;
  if (!Number.isFinite(exp) || exp <= 0) return null;
  if (!Number.isFinite(ver) || ver <= 0) return null;
  if (!username) return null;

  return {
    id,
    username,
    display_name: value.display_name == null ? null : String(value.display_name),
    email: value.email == null ? null : String(value.email),
    roles,
    is_admin: isAdmin,
    ver,
    exp
  };
}

export function parsePrincipalCookie(raw: string): PrincipalSnapshot | null {
  if (!raw || typeof raw !== 'string') return null;

  const [payloadB64] = raw.split('.', 1);
  if (!payloadB64) return null;

  try {
    const decoded = base64UrlDecode(payloadB64);
    const parsed = JSON.parse(decoded) as unknown;
    return toSnapshot(parsed);
  } catch {
    return null;
  }
}

export async function verifyPrincipalCookie(raw: string): Promise<PrincipalSnapshot | null> {
  if (!raw || typeof raw !== 'string') return null;

  const parts = raw.split('.');
  if (parts.length !== 2) return null;

  const [payloadB64, sig] = parts;
  if (!payloadB64 || !sig) return null;

  const ok = await verifySignature(payloadB64, sig, DEFAULT_SIGNING_KEY);
  if (!ok) {
    return null;
  }

  return parsePrincipalCookie(raw);
}

export function isPrincipalExpired(snapshot: PrincipalSnapshot): boolean {
  const now = Math.floor(Date.now() / 1000);
  return snapshot.exp <= now;
}

export function principalToMe(snapshot: PrincipalSnapshot): Me {
  const isAdmin = snapshot.roles.some((role) => {
    const normalized = String(role).toLowerCase();
    return normalized === 'platform_admin' || normalized === 'admin';
  });
  return {
    id: snapshot.id,
    username: snapshot.username,
    display_name: snapshot.display_name ?? null,
    email: snapshot.email ?? null,
    roles: [...snapshot.roles],
    is_admin: isAdmin
  };
}

export function clearAuthCookies(cookies: Cookies): void {
  cookies.delete(DEFAULT_SESSION_COOKIE_NAME, { path: '/' });
  cookies.delete(DEFAULT_PRINCIPAL_COOKIE_NAME, { path: '/' });
}

export async function issuePrincipalCookieFromMe(
  me: Me,
  ttlSeconds: number,
  signingKey = DEFAULT_SIGNING_KEY
): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + Math.max(1, ttlSeconds);

  const snapshot: PrincipalSnapshot = {
    id: me.id,
    username: me.username,
    display_name: me.display_name ?? null,
    email: me.email ?? null,
    roles: Array.isArray(me.roles) ? me.roles.map((r) => String(r)) : [],
    is_admin: me.roles.some((role) => {
      const normalized = String(role).toLowerCase();
      return normalized === 'platform_admin' || normalized === 'admin';
    }),
    ver: 1,
    exp
  };

  const payload = JSON.stringify(snapshot);
  const payloadB64 = base64UrlEncode(payload);
  const signature = await sign(payloadB64, signingKey);
  return `${payloadB64}.${signature}`;
}

export async function verifyPrincipalCookieWithKey(
  raw: string,
  signingKey = DEFAULT_SIGNING_KEY
): Promise<PrincipalSnapshot | null> {
  if (!raw || typeof raw !== 'string') return null;

  const parts = raw.split('.');
  if (parts.length !== 2) return null;

  const [payloadB64, sig] = parts;
  if (!payloadB64 || !sig) return null;

  const ok = await verifySignature(payloadB64, sig, signingKey);
  if (!ok) {
    return null;
  }

  return parsePrincipalCookie(raw);
}

export function clearAuthCookiesWithNames(
  cookies: Cookies,
  names: AuthCookieNames = {}
): void {
  const sessionCookieName =
    names.sessionCookieName && names.sessionCookieName.trim() !== ''
      ? names.sessionCookieName
      : DEFAULT_SESSION_COOKIE_NAME;
  const principalCookieName =
    names.principalCookieName && names.principalCookieName.trim() !== ''
      ? names.principalCookieName
      : DEFAULT_PRINCIPAL_COOKIE_NAME;

  cookies.delete(sessionCookieName, { path: '/' });
  cookies.delete(principalCookieName, { path: '/' });
}
