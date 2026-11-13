import { writable, type Readable } from 'svelte/store';

/**
 * Live updates pushed by the server (/live, Server-Sent Events): unread notices, waiting requests, critical alerts
 * and the tasks in progress. One connection per tab, opened by the app layout; the browser reconnects by itself.
 */
export type LiveNotice = { id: number; kind: string; severity: string; title: string; link: string | null };
export type LiveTask = {
  id: number;
  action: string | null;
  job_type: string | null;
  status: string;
  stuck: string | null;
  target: { label: string; href: string | null } | null;
  started_at: string | null;
  run_seconds: number | null;
  progress: Record<string, unknown> | null;
};
export type LiveState = {
  connected: boolean;
  unread: number;
  latest: LiveNotice | null;
  pending: number | null;
  critical: number | null;
  requestsStamp: string | null;
  alertsStamp: string | null;
  tasks: LiveTask[];
};

const initial: LiveState = {
  connected: false, unread: 0, latest: null, pending: null, critical: null, requestsStamp: null, alertsStamp: null, tasks: []
};
const state = writable<LiveState>(initial);
export const live: Readable<LiveState> = { subscribe: state.subscribe };

/** Notices read in the bell: the count follows at once, the server confirms on its next pulse */
export function markNoticesRead(count: number | 'all') {
  state.update((s) => ({ ...s, unread: count === 'all' ? 0 : Math.max(0, s.unread - count) }));
}

let source: EventSource | null = null;
let users = 0;

export function connectLive(): () => void {
  users += 1;
  if (!source && typeof EventSource !== 'undefined') {
    source = new EventSource('/live');
    source.addEventListener('open', () => state.update((s) => ({ ...s, connected: true })));
    source.addEventListener('error', () => state.update((s) => ({ ...s, connected: false })));
    source.addEventListener('pulse', (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as Record<string, any>;
        state.update((s) => ({
          ...s,
          connected: true,
          unread: Number(data.unread ?? 0) || 0,
          latest: data.latest ? { ...data.latest, id: Number(data.latest.id) } : null,
          pending: data.pending == null ? s.pending : Number(data.pending) || 0,
          critical: data.alerts_stamp == null ? s.critical : Number(data.critical_open ?? 0) || 0,
          requestsStamp: data.requests_stamp ?? null,
          alertsStamp: data.alerts_stamp ?? null
        }));
      } catch {
        /* a malformed message is skipped */
      }
    });
    source.addEventListener('tasks', (event) => {
      try {
        const tasks = JSON.parse((event as MessageEvent).data) as LiveTask[];
        state.update((s) => ({ ...s, tasks: Array.isArray(tasks) ? tasks : [] }));
      } catch {
        /* skipped */
      }
    });
    // The session ended: no reconnection loop, the next navigation goes to the sign-in page
    source.addEventListener('signed-out', () => {
      source?.close();
      source = null;
      state.set(initial);
    });
  }
  return () => {
    users -= 1;
    if (users <= 0 && source) {
      source.close();
      source = null;
      users = 0;
      state.set(initial);
    }
  };
}

/**
 * Calls `run` each time `pick(state)` changes after the first value (a stamp of requests or alerts moved):
 * the page reloads its data without the person asking.
 */
export function onLiveChange(pick: (s: LiveState) => unknown, run: () => void): () => void {
  let first = true;
  let previous: unknown;
  return live.subscribe((s) => {
    const value = pick(s);
    if (value == null) return;
    if (first) {
      first = false;
      previous = value;
      return;
    }
    if (value !== previous) {
      previous = value;
      run();
    }
  });
}
