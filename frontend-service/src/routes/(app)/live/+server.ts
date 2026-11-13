import type { RequestHandler } from './$types';
import { normalizeMe } from '$lib/types/me';
import { apiServerGet } from '$lib/server/api-server';

/**
 * Live updates of the app (Server-Sent Events): the browser keeps one connection open, the server reads the pulse of
 * the person every few seconds and pushes only what changed — unread notices, waiting requests, critical alerts,
 * tasks in progress (administrators). The pages refresh themselves when their data moved.
 */
const TICK_MS = 5000;
const TASKS_EVERY = 2; // tasks (administrators) every 2 ticks: their list costs more than the pulse

type Envelope<T> = { data?: T; items?: T };
const unwrap = <T>(value: unknown): T | null => {
  if (value && typeof value === 'object' && 'data' in (value as object)) return ((value as Envelope<T>).data ?? null) as T | null;
  return (value ?? null) as T | null;
};
const listOf = (value: unknown): unknown[] => {
  if (Array.isArray(value)) return value;
  const v = value as { data?: unknown; items?: unknown } | null;
  if (Array.isArray(v?.data)) return v.data as unknown[];
  if (Array.isArray(v?.items)) return v.items as unknown[];
  return [];
};

export const GET: RequestHandler = async (event) => {
  const me = normalizeMe((event.locals as { me?: unknown }).me ?? null);
  const admin = me?.is_admin === true;
  const encoder = new TextEncoder();
  let timer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let last = '';
      let lastRequests: string | null = null;
      let pending: number | null = null;
      let tick = 0;
      let lastTasks = '';

      const send = (name: string, payload: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`));
        } catch {
          closed = true;
        }
      };
      const stop = () => {
        if (closed) return;
        closed = true;
        if (timer) clearTimeout(timer);
        try { controller.close(); } catch { /* already closed */ }
      };

      const run = async () => {
        if (closed) return;
        try {
          const pulse = unwrap<Record<string, unknown>>(await apiServerGet('/me/pulse', event)) ?? {};
          // The waiting requests are counted again only when a request moved
          if (pulse.requests_stamp !== lastRequests || pending === null) {
            lastRequests = (pulse.requests_stamp as string | null) ?? null;
            const counts = unwrap<Record<string, number>>(await apiServerGet('/access-requests/counts-by-status', event).catch(() => null));
            pending = Number(counts?.pending ?? pending ?? 0) || 0;
          }
          const state = { ...pulse, pending };
          const fingerprint = JSON.stringify(state);
          if (fingerprint !== last) {
            last = fingerprint;
            send('pulse', state);
          }
          if (admin && tick % TASKS_EVERY === 0) {
            const jobs = listOf(await apiServerGet('/admin/jobs?active_only=true&limit=20', event).catch(() => []));
            const tasks = jobs.slice(0, 12).map((raw) => {
              const job = raw as Record<string, any>;
              return {
                id: job.id, action: job.action, job_type: job.job_type, status: job.status, stuck: job.stuck ?? null,
                target: job.target ? { label: job.target.label, href: job.target.href ?? null } : null,
                started_at: job.started_at ?? null, run_seconds: job.run_seconds ?? null, progress: job.progress ?? null
              };
            });
            const key = JSON.stringify(tasks);
            if (key !== lastTasks) {
              lastTasks = key;
              send('tasks', tasks);
            }
          }
          tick += 1;
          if (tick % 6 === 0) send('ping', Date.now()); // keeps proxies from closing a quiet connection
        } catch (error) {
          const status = (error as { status?: number })?.status;
          if (status === 401 || status === 403) {
            send('signed-out', {});
            stop();
            return;
          }
        }
        if (!closed) timer = setTimeout(run, TICK_MS);
      };
      send('ready', { tick_ms: TICK_MS });
      void run();
    },
    cancel() {
      closed = true;
      if (timer) clearTimeout(timer);
    }
  });

  return new Response(stream, {
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'x-accel-buffering': 'no'
    }
  });
};
