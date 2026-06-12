import type { FetchLike, HttpRequestOptions } from './contract';
import { ApiError, normalizeErrorMessage } from './errors';

const LOG_LEVEL = String((import.meta as any).env?.VITE_LOG_LEVEL ?? 'INFO').trim().toUpperCase();
const DEBUG_HTTP = LOG_LEVEL === 'DEBUG' || LOG_LEVEL === 'TRACE';

export function normalizePath(path: string, basePath: string = '/api'): string {
  const normalizedBase = basePath.startsWith('/') ? basePath : '/api';
  const sanitizedBase = normalizedBase.endsWith('/') ? normalizedBase.slice(0, -1) : normalizedBase;

  const p = path.startsWith('/') ? path : `/${path}`;
  if (p === sanitizedBase || p.startsWith(`${sanitizedBase}/`)) {
    return p;
  }
  return `${sanitizedBase}${p}`;
}

export function buildUrl(path: string, params?: Record<string, unknown>, basePath: string = '/api'): string {
  const safePath = normalizePath(path, basePath);
  const url = new URL(safePath, 'http://local');

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue;
      url.searchParams.set(k, String(v));
    }
  }

  return url.pathname + (url.search ? url.search : '');
}

export async function parseJsonSafe(res: Response): Promise<unknown> {
  const ct = res.headers.get('content-type') ?? '';

  if (ct.includes('application/json')) {
    return await res.json();
  }

  const text = await res.text();
  if (!text) return null;

  const trimmed = text.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      // ignore json parse fallback
    }
  }

  return { message: text };
}

export async function httpRequest<T>(fetchFn: FetchLike, options: HttpRequestOptions): Promise<T> {
  const {
    method,
    path,
    body,
    params,
    headers,
    timeoutMs = 15000,
    credentials = 'include',
    basePath = '/api'
  } = options;

  const url = buildUrl(path, params, basePath);

  if (DEBUG_HTTP) {
    console.debug('[http] request', { method, url, timeoutMs, params, body });
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const reqHeaders = new Headers(headers ?? {});
  const init: RequestInit = {
    method,
    credentials,
    signal: controller.signal,
    headers: reqHeaders
  };

  if (body !== undefined && method !== 'GET' && method !== 'HEAD') {
    if (!reqHeaders.has('content-type')) {
      reqHeaders.set('content-type', 'application/json');
    }
    init.body = JSON.stringify(body);
  }

  let res: Response;

  try {
    res = await fetchFn(url, init);
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('Request timeout', {
        code: 'REQUEST_TIMEOUT',
        transport: 'timeout'
      });
    }
    throw new ApiError('Network error', {
      code: 'NETWORK_ERROR',
      transport: 'network',
      details: err
    });
  } finally {
    clearTimeout(timeoutId);
  }

  const data = await parseJsonSafe(res);

  if (DEBUG_HTTP) {
    console.debug('[http] response', { method, url, status: res.status, ok: res.ok, data });
  }

  const dataRec = data && typeof data === 'object' && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : {};
  const nestedError = dataRec.error && typeof dataRec.error === 'object' && !Array.isArray(dataRec.error)
    ? (dataRec.error as Record<string, unknown>)
    : null;

  if (!res.ok) {
    throw new ApiError(normalizeErrorMessage(res.status, data, res.statusText), {
      status: res.status,
      code:
        (typeof nestedError?.code === 'string' ? nestedError.code : undefined) ??
        (typeof dataRec.code === 'string' ? dataRec.code : undefined),
      requestId:
        (typeof dataRec.requestId === 'string' ? dataRec.requestId : undefined) ??
        (typeof dataRec.request_id === 'string' ? dataRec.request_id : undefined),
      transport: 'http',
      details: data
    });
  }

  return data as T;
}
