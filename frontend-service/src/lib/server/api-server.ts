/**
 * SERVER-ONLY API helper (BFF)
 *
 * - Read-only (GET): server loads never mutate; writes go through the browser client.
 * - Forwards the user's session cookie to the gateway.
 */

import type { RequestEvent } from '@sveltejs/kit';

import { httpRequest } from '$lib/api/http/request';
import { unwrapDataStrict, unwrapListStrict } from '$lib/api/http/envelopes';

export function apiServerGet<T = unknown>(path: string, event?: RequestEvent): Promise<T> {
  const headers = new Headers();
  const cookieHeader = event?.request?.headers?.get('cookie');
  if (cookieHeader) {
    headers.set('cookie', cookieHeader);
  }

  return httpRequest<T>(event?.fetch ?? fetch, {
    method: 'GET',
    path,
    headers,
    basePath: '/api',
    credentials: 'include'
  });
}

export const apiServerGetData = async <T>(p: string, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerGet(p, event), `GET ${p}`);

export const apiServerGetList = async <T>(p: string, event?: RequestEvent): Promise<T[]> =>
  unwrapListStrict<T>(await apiServerGet(p, event), `GET ${p}`);
