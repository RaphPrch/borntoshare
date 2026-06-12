/**
 * SERVER-ONLY API helper (BFF)
 *
 * V1 (CURRENT):
 * - HTTP only
 * - Cookie session
 * - CSRF disabled by default
 * - Frontend BFF routes calls directly to backend services
 *
 * V2 (FUTURE):
 * - CSRF can be enabled via env
 * - Same helper reused without UI refactor
 */

import type { RequestEvent } from '@sveltejs/kit';

import { serverRequest } from '$lib/http/server-request';
import { unwrapDataStrict, unwrapListStrict } from '$lib/http/envelopes';

export async function apiRequest(
  path: string,
  params: {
    event?: RequestEvent;
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    body?: unknown;
    timeoutMs?: number;
  } = {}
) {
  const { event, method = 'GET', body, timeoutMs } = params;
  return serverRequest(path, {
    event,
    method,
    body,
    timeoutMs
  });
}

export const apiServerGet = (p: string, event?: RequestEvent) =>
  apiRequest(p, { method: 'GET', event });

export const apiServerPost = (p: string, body: unknown, event?: RequestEvent) =>
  apiRequest(p, { method: 'POST', body, event });

export const apiServerPut = (p: string, body: unknown, event?: RequestEvent) =>
  apiRequest(p, { method: 'PUT', body, event });

export const apiServerPatch = (p: string, body: unknown, event?: RequestEvent) =>
  apiRequest(p, { method: 'PATCH', body, event });

export const apiServerDelete = (p: string, event?: RequestEvent) =>
  apiRequest(p, { method: 'DELETE', event });

export const apiServerGetData = async <T>(p: string, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerGet(p, event), `GET ${p}`);

export const apiServerGetList = async <T>(p: string, event?: RequestEvent): Promise<T[]> =>
  unwrapListStrict<T>(await apiServerGet(p, event), `GET ${p}`);

export const apiServerPostData = async <T>(p: string, body: unknown, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerPost(p, body, event), `POST ${p}`);

export const apiServerPutData = async <T>(p: string, body: unknown, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerPut(p, body, event), `PUT ${p}`);

export const apiServerPatchData = async <T>(p: string, body: unknown, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerPatch(p, body, event), `PATCH ${p}`);

export const apiServerDeleteData = async <T>(p: string, event?: RequestEvent): Promise<T> =>
  unwrapDataStrict<T>(await apiServerDelete(p, event), `DELETE ${p}`);
