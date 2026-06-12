import { derived, writable } from 'svelte/store';

import { listActivityLatest, type ActivityEvent } from '../../api/activity';
import type { FetchLike } from '../../api/client';

import { frontendLogs, logError, logInfo, logWarning } from './logger';
import type { FrontendLogEvent } from './types';

export type UiActivityLevel = 'info' | 'warning' | 'error';

export type UiActivityEntry = {
  id: string;
  ts: number;
  level: UiActivityLevel;
  message: string;
  context?: Record<string, unknown>;
  source?: 'ui' | 'db';
};

type UiLogLevel = UiActivityLevel;

const activityDbSeed = writable<UiActivityEntry[]>([]);

function uuid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${String(Math.random()).slice(2)}`;
  }
}

function toUiLevel(level: FrontendLogEvent['level']): UiActivityLevel {
  if (level === 'error') return 'error';
  if (level === 'warning') return 'warning';
  return 'info';
}

function toUiMessage(event: ActivityEvent): string {
  return String(event?.target_display ?? event?.action ?? 'event');
}

function toUiLevelFromActivity(event: ActivityEvent): UiActivityLevel {
  const value = String(event?.severity ?? event?.outcome ?? '').toLowerCase();
  if (value.includes('error') || value.includes('fail')) return 'error';
  if (value.includes('warn')) return 'warning';
  return 'info';
}

export const uiActivityLogs = derived(
  [frontendLogs, activityDbSeed],
  ([$frontendLogs, $activityDbSeed]): UiActivityEntry[] => {
    const runtimeRows = $frontendLogs.map((event): UiActivityEntry => ({
      id: uuid(),
      ts: new Date(event.ts).getTime(),
      level: toUiLevel(event.level),
      message: event.message,
      context: event.context,
      source: event.source === 'ui' ? 'ui' : 'db'
    }));
    return [...runtimeRows, ...$activityDbSeed]
      .sort((a, b) => b.ts - a.ts)
      .slice(0, 300);
  }
);

export function pushUiActivityLog(
  level: UiLogLevel,
  message: string,
  context?: Record<string, unknown>,
  source: 'ui' | 'db' = 'ui'
): void {
  const mergedContext = {
    ...(context ?? {}),
    uiSource: source
  };

  if (level === 'error') {
    logError(message, mergedContext);
    return;
  }

  if (level === 'warning') {
    logWarning(message, mergedContext);
    return;
  }

  logInfo(message, mergedContext);
}

export async function hydrateUiActivityLogs(fetchFn: FetchLike, limit = 120): Promise<void> {
  const events = await listActivityLatest(fetchFn, limit);
  const mapped = events.map((event): UiActivityEntry => ({
    id: uuid(),
    ts: new Date(String(event?.created_at ?? event?.event_time ?? new Date().toISOString())).getTime(),
    level: toUiLevelFromActivity(event),
    message: toUiMessage(event),
    context: {
      action: event?.action,
      outcome: event?.outcome,
      event
    },
    source: 'db'
  }));
  activityDbSeed.set(mapped);
}

