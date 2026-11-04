import type { RequestHandler } from './$types';

import { buildInternalHeaders } from '$lib/server/internal-token';

/**
 * Platform state for a supervision tool (Advanced Settings › Extensions › Centreon), with its read-only token
 * (header X-Monitoring-Token, or ?token=). 200 « OK - … » / « WARNING - … », 503 « CRITICAL - … »: check_http reads it.
 */
export const GET: RequestHandler = async ({ request, url, fetch }) => {
  const token = (request.headers.get('x-monitoring-token') ?? url.searchParams.get('token') ?? '').trim();
  const text = (status: number, body: string) => new Response(`${body}\n`, { status, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
  if (!token) return text(401, 'UNKNOWN - monitoring token missing');
  const core = String(process.env.B2S_CORE_URL ?? '').replace(/\/+$/, '');
  try {
    const response = await fetch(`${core}/extensions/centreon/check`, { headers: { ...(await buildInternalHeaders()), 'x-monitoring-token': token } });
    if (response.status === 401) return text(401, 'UNKNOWN - monitoring token refused');
    const body = await response.json();
    const data = body?.data ?? {};
    return text(data.state === 'CRITICAL' ? 503 : 200, String(data.text ?? 'UNKNOWN - no answer'));
  } catch {
    return text(503, 'CRITICAL - BornToShare core-service does not answer');
  }
};
