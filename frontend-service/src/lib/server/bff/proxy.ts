import type { RequestEvent } from '@sveltejs/kit';

import { buildInternalHeaders } from '../internal-token';
import { getServiceBaseUrl, resolveDirectRoute } from '../service-routes';

type BffMe = {
  id?: number | string | null;
  identity_id?: number | string | null;
  username?: string | null;
  display_name?: string | null;
  roles?: string[] | null;
  is_admin?: boolean | number | string | null;
};

function createRequestId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${String(Math.random()).slice(2)}`;
  }
}

function resolveRequestId(event: RequestEvent): string {
  const forwarded = event.request.headers.get('x-request-id');
  if (forwarded && forwarded.trim()) {
    return forwarded.trim();
  }
  return createRequestId();
}

function normalizeIdentityId(me: BffMe | null | undefined): string | null {
  const value = me?.identity_id ?? me?.id;
  const raw = String(value ?? '').trim();
  return /^\d+$/.test(raw) ? raw : null;
}

function normalizeRoles(me: BffMe | null | undefined): string[] {
  const roles = Array.isArray(me?.roles) ? me.roles : [];
  const normalized = roles.map((value) => String(value).trim().toLowerCase()).filter(Boolean);
  return Array.from(new Set(normalized));
}

function canAccessAdminRoutes(path: string, roles: string[]): boolean {
  if (path.startsWith('/storage-endpoints')) {
    return roles.includes('platform_admin');
  }
  if (path.startsWith('/activity/latest') || path.startsWith('/activity/by-actor')) {
    return roles.includes('platform_admin');
  }
  if (path.startsWith('/identity') || path.startsWith('/identity-sources')) {
    return roles.includes('platform_admin');
  }
  if (
    path.startsWith('/access-profiles') ||
    path.startsWith('/zones') ||
    path.startsWith('/naming-policies') ||
    path.startsWith('/admin/')
  ) {
    return roles.includes('platform_admin');
  }
  if (path === '/admin/jobs' || path.startsWith('/admin/jobs/')) {
    return roles.includes('platform_admin');
  }
  return true;
}

const jsonError = (
  status: number,
  message: string,
  code: string,
  requestId: string,
  details?: Record<string, unknown>
): Response =>
  new Response(
    JSON.stringify({
      error: {
        code,
        message,
        details: {
          retryable: status >= 500,
          ...(details ?? {})
        },
        request_id: requestId
      }
    }),
    {
      status,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'x-request-id': requestId
      }
    }
  );

async function readUpstreamPayload(upstream: Response): Promise<unknown> {
  const contentType = upstream.headers.get('content-type') ?? '';
  const raw = await upstream.text();
  if (!raw.trim()) return null;
  if (contentType.includes('application/json') || raw.trim().startsWith('{') || raw.trim().startsWith('[')) {
    try {
      return JSON.parse(raw);
    } catch {
      return { message: raw };
    }
  }
  return { message: raw };
}

function upstreamMessage(payload: unknown, fallback: string): string {
  const isGenericHttpMessage = (value: string) =>
    ['bad request', 'unprocessable entity', 'internal server error'].includes(value.trim().toLowerCase());

  const useful = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    if (!trimmed || isGenericHttpMessage(trimmed)) return null;
    return trimmed;
  };

  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return fallback;
  const rec = payload as Record<string, unknown>;
  const nestedError = rec.error && typeof rec.error === 'object' && !Array.isArray(rec.error)
    ? (rec.error as Record<string, unknown>)
    : null;

  if (nestedError) {
    for (const key of ['message', 'code', 'error_code', 'hint']) {
      const value = useful(nestedError[key]);
      if (value) return value;
    }
  }

  const detail = rec.detail;
  const directDetail = useful(detail);
  if (directDetail) return directDetail;

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const detailRec = detail as Record<string, unknown>;
    for (const key of ['message', 'error_code', 'hint']) {
      const value = useful(detailRec[key]);
      if (value) return value;
    }
  }
  for (const key of ['message', 'error']) {
    const value = useful(rec[key]);
    if (value) return value;
  }
  return fallback;
}

async function readRequestBody(request: Request): Promise<ArrayBuffer | undefined> {
  if (request.method === 'GET' || request.method === 'HEAD') {
    return undefined;
  }
  return request.arrayBuffer();
}

export function buildUpstreamUrl(baseUrl: string, routePath: string, search: string = ''): URL {
  const target = new URL(baseUrl);
  const basePath = target.pathname.replace(/\/+$/, '');
  const path = routePath.startsWith('/') ? routePath : `/${routePath}`;

  target.pathname = `${basePath}${path}`.replace(/\/{2,}/g, '/') || '/';
  target.search = search;

  return target;
}

export async function proxyApi(event: RequestEvent): Promise<Response> {
  const { request, url } = event;
  const requestId = resolveRequestId(event);
  const route = resolveDirectRoute(url.pathname);

  if (!route) {
    return jsonError(404, 'API route not found', 'BFF_ROUTE_NOT_FOUND', requestId);
  }

  const baseUrl = getServiceBaseUrl(route.service);
  if (!baseUrl) {
    return jsonError(503, 'Upstream service unavailable', 'BFF_SERVICE_UNAVAILABLE', requestId);
  }

  const target = buildUpstreamUrl(baseUrl, route.path, url.search);

  const headers = new Headers(request.headers);
  headers.delete('host');

  headers.set('x-forwarded-host', url.host);
  headers.set('x-forwarded-proto', url.protocol.replace(':', ''));
  headers.set('x-forwarded-for', event.getClientAddress());
  headers.set('x-request-id', requestId);

  const me = (event.locals as { me?: BffMe | null })?.me ?? null;
  const identityId = normalizeIdentityId(me);
  const roles = normalizeRoles(me);
  const actorDisplay = String(me?.display_name ?? me?.username ?? '').trim();

  if (!canAccessAdminRoutes(route.path, roles)) {
    return jsonError(403, 'Forbidden', 'BFF_FORBIDDEN', requestId, { path: route.path });
  }

  if (identityId) {
    headers.set('x-identity-id', identityId);
  }
  if (roles.length > 0) {
    headers.set('x-roles', roles.join(','));
  }
  if (actorDisplay) {
    headers.set('x-actor-display', actorDisplay);
  }

  if (route.internal) {
    const internalHeaders = await buildInternalHeaders();
    for (const [key, value] of Object.entries(internalHeaders as Record<string, string>)) {
      headers.set(key, value);
    }
  }

  try {
    const upstream = await fetch(target.toString(), {
      method: request.method,
      headers,
      body: await readRequestBody(request),
      redirect: 'manual'
    });

    const responseHeaders = new Headers(upstream.headers);
    if (!responseHeaders.get('x-request-id')) {
      responseHeaders.set('x-request-id', requestId);
    }

    if (!upstream.ok) {
      const payload = await readUpstreamPayload(upstream);
      const message = upstreamMessage(payload, upstream.statusText || 'Upstream request failed');
      const normalizedMessage = ['bad request', 'unprocessable entity'].includes(message.toLowerCase())
        ? 'The request was rejected by the service. Check the form values and try again.'
        : message;

      console.warn('[bff] upstream_error', {
        requestId,
        status: upstream.status,
        statusText: upstream.statusText,
        service: route.service,
        path: route.path,
        target: target.toString(),
        message,
        payload
      });

      return jsonError(
        upstream.status,
        normalizedMessage,
        upstream.status === 400 ? 'BFF_UPSTREAM_BAD_REQUEST' : 'BFF_UPSTREAM_ERROR',
        requestId,
        {
          service: route.service,
          path: route.path,
          upstream_status: upstream.status,
          upstream_detail: payload
        }
      );
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders
    });
  } catch {
    return jsonError(502, 'Failed to reach upstream service', 'BFF_UPSTREAM_UNREACHABLE', requestId);
  }
}
