import type { RequestEvent } from '@sveltejs/kit';

import { httpRequest } from './request';
import type { HttpMethod } from './contract';

declare const process: {
  env: Record<string, string | undefined>;
};

const CSRF_ENABLED = (process.env.B2S_CSRF_ENABLED ?? 'false') === 'true';
const CSRF_COOKIE = 'b2s_csrf';
const CSRF_HEADER = 'x-csrf-token';

function getCookieValue(cookieHeader: string | null | undefined, name: string): string | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(';')) {
    const [k, ...rest] = part.trim().split('=');
    if (k === name) return decodeURIComponent(rest.join('='));
  }
  return null;
}

async function ensureCsrfToken(event: RequestEvent): Promise<string | null> {
  if (!CSRF_ENABLED) return null;

  const fromEvent = event.cookies?.get(CSRF_COOKIE);
  if (fromEvent) return fromEvent;

  const cookieHeader = event.request?.headers?.get('cookie') || '';
  const fromHeader = getCookieValue(cookieHeader, CSRF_COOKIE);
  if (fromHeader) return fromHeader;

  const res = await event.fetch('/api/csrf', {
    method: 'GET',
    headers: cookieHeader ? { cookie: cookieHeader } : undefined
  });

  if (!res.ok) return null;
  const data = await res.json().catch(() => null);
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return null;
  }
  const rec = data as Record<string, unknown>;
  const body =
    rec.ok === true && rec.data && typeof rec.data === 'object' && !Array.isArray(rec.data)
      ? (rec.data as Record<string, unknown>)
      : rec;
  return typeof body.csrf_token === 'string' ? body.csrf_token : null;
}

export async function serverRequest<T>(
  path: string,
  params: {
    event?: RequestEvent;
    method?: HttpMethod;
    body?: unknown;
    timeoutMs?: number;
  } = {}
): Promise<T> {
  const { event, method = 'GET', body, timeoutMs } = params;

  const fetcher = event?.fetch ?? fetch;
  const headers = new Headers();

  const cookieHeader = event?.request?.headers?.get('cookie');
  if (cookieHeader) {
    headers.set('cookie', cookieHeader);
  }

  if (
    event &&
    CSRF_ENABLED &&
    (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE')
  ) {
    const csrf = await ensureCsrfToken(event);
    if (csrf) headers.set(CSRF_HEADER, csrf);
  }

  return httpRequest<T>(fetcher, {
    method,
    path,
    body,
    headers,
    timeoutMs,
    basePath: '/api',
    credentials: 'include'
  });
}
