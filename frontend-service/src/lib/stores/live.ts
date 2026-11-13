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

// One connection per browser, not per tab: the tab holding the lock « b2s-live » (Web Locks) opens /live and relays
// what it receives to the other tabs (BroadcastChannel); when it closes, another tab takes the lock and the connection.
// A browser without these APIs connects each tab itself.
const CHANNEL = 'b2s-live';
let channel: BroadcastChannel | null = null;
let source: EventSource | null = null;
let releaseLock: (() => void) | null = null;
let users = 0;
const lastMessages = new Map<string, string>();

function applyMessage(name: string, raw: string) {
  try {
    const data = JSON.parse(raw);
    if (name === 'pulse') {
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
    } else if (name === 'tasks') {
      state.update((s) => ({ ...s, tasks: Array.isArray(data) ? data : [] }));
    } else if (name === 'signed-out') {
      state.set(initial);
    }
  } catch {
    /* a malformed message is skipped */
  }
}

function openSource() {
  source = new EventSource('/live');
  source.addEventListener('open', () => state.update((s) => ({ ...s, connected: true })));
  source.addEventListener('error', () => state.update((s) => ({ ...s, connected: false })));
  for (const name of ['pulse', 'tasks', 'signed-out']) {
    source.addEventListener(name, (event) => {
      const raw = (event as MessageEvent).data as string;
      lastMessages.set(name, raw);
      applyMessage(name, raw);
      channel?.postMessage({ name, raw });
      // The session ended: no reconnection loop, the next navigation goes to the sign-in page
      if (name === 'signed-out') closeSource();
    });
  }
}

function closeSource() {
  source?.close();
  source = null;
}

export function connectLive(): () => void {
  users += 1;
  if (users === 1 && typeof EventSource !== 'undefined') {
    const locks = (typeof navigator !== 'undefined' ? (navigator as Navigator & { locks?: LockManager }).locks : undefined);
    if (typeof BroadcastChannel !== 'undefined' && locks) {
      channel = new BroadcastChannel(CHANNEL);
      channel.onmessage = (event: MessageEvent<{ name: string; raw?: string }>) => {
        const { name, raw } = event.data ?? {};
        // A tab that just opened asks the relay for the last state (the server only sends what changes)
        if (name === 'hello') {
          if (source) lastMessages.forEach((value, key) => channel?.postMessage({ name: key, raw: value }));
          return;
        }
        if (name && raw != null) applyMessage(name, raw);
      };
      channel.postMessage({ name: 'hello' });
      void locks.request(CHANNEL, () => new Promise<void>((resolve) => {
        releaseLock = () => { closeSource(); resolve(); };
        if (users > 0) openSource(); else resolve();
      })).catch(() => undefined);
    } else {
      openSource();
    }
  }
  return () => {
    users -= 1;
    if (users > 0) return;
    users = 0;
    closeSource();
    releaseLock?.();
    releaseLock = null;
    channel?.close();
    channel = null;
    lastMessages.clear();
    state.set(initial);
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
