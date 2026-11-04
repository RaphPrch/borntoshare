import type { RequestHandler } from './$types';

import { buildInternalHeaders } from '$lib/server/internal-token';

/**
 * Figures of the platform in the Prometheus text format, for Prometheus / Grafana (Advanced Settings › Extensions ›
 * Grafana), with the metrics token of the extension: « Authorization: Bearer <token> » or X-Monitoring-Token.
 */
export const GET: RequestHandler = async ({ request, fetch }) => {
  const bearer = (request.headers.get('authorization') ?? '').replace(/^Bearer\s+/i, '');
  const token = (request.headers.get('x-monitoring-token') ?? bearer).trim();
  const plain = (status: number, body: string) =>
    new Response(body, { status, headers: { 'content-type': 'text/plain; version=0.0.4; charset=utf-8', 'cache-control': 'no-store' } });
  if (!token) return plain(401, 'metrics token missing\n');
  const core = String(process.env.B2S_CORE_URL ?? '').replace(/\/+$/, '');
  try {
    const response = await fetch(`${core}/extensions/grafana/metrics`, { headers: { ...(await buildInternalHeaders()), 'x-monitoring-token': token } });
    if (response.status === 401) return plain(401, 'metrics token refused\n');
    const body = await response.json();
    return plain(200, String(body?.data?.text ?? ''));
  } catch {
    return plain(503, 'core-service does not answer\n');
  }
};
