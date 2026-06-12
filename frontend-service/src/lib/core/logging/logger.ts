import { writable } from 'svelte/store';

import type { AppError } from '../errors/types';
import { toAppError } from '../errors';

import { createConsoleTransport, createHttpTransport } from './transports';
import type {
  AppErrorLogContext,
  FrontendLogEvent,
  FrontendLogLevel,
  FrontendLogSource,
  LoggerTransport
} from './types';

const MAX_IN_MEMORY_LOGS = 300;

const DEFAULT_SOURCE_BY_LEVEL: Record<FrontendLogLevel, FrontendLogSource> = {
  debug: 'ui',
  info: 'ui',
  warning: 'ui',
  error: 'runtime'
};

type LoggerOptions = {
  transports?: LoggerTransport[];
};

export const frontendLogs = writable<FrontendLogEvent[]>([]);

const DEFAULT_TRANSPORTS: LoggerTransport[] = [
  createConsoleTransport()
];

const transportEndpoint =
  String((import.meta as { env?: Record<string, string | undefined> }).env?.VITE_FRONTEND_LOG_ENDPOINT ?? '').trim();

if (transportEndpoint) {
  DEFAULT_TRANSPORTS.push(createHttpTransport({ endpoint: transportEndpoint }));
}

let activeTransports: LoggerTransport[] = [...DEFAULT_TRANSPORTS];
let runtimeHandlersInstalled = false;

function routeFromLocation(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  return window.location?.pathname;
}

function toContextObject(context?: Record<string, unknown>): Record<string, unknown> | undefined {
  if (!context) return undefined;
  return Object.keys(context).length > 0 ? context : undefined;
}

function enqueue(event: FrontendLogEvent): void {
  frontendLogs.update((prev) => [event, ...prev].slice(0, MAX_IN_MEMORY_LOGS));
}

function dispatch(event: FrontendLogEvent): void {
  enqueue(event);
  for (const transport of activeTransports) {
    try {
      const result = transport.send(event);
      if (result && typeof (result as Promise<unknown>).then === 'function') {
        void result;
      }
    } catch {
      // ignore transport errors
    }
  }
}

function buildEvent(
  level: FrontendLogLevel,
  message: string,
  context?: Record<string, unknown>
): FrontendLogEvent {
  return {
    ts: new Date().toISOString(),
    level,
    message,
    source: DEFAULT_SOURCE_BY_LEVEL[level],
    route: routeFromLocation(),
    context: toContextObject(context)
  };
}

export function configureLogger(options: LoggerOptions): void {
  activeTransports = options.transports && options.transports.length > 0
    ? [...options.transports]
    : [...DEFAULT_TRANSPORTS];
}

export function logDebug(message: string, context?: Record<string, unknown>): void {
  dispatch(buildEvent('debug', message, context));
}

export function logInfo(message: string, context?: Record<string, unknown>): void {
  dispatch(buildEvent('info', message, context));
}

export function logWarning(message: string, context?: Record<string, unknown>): void {
  dispatch(buildEvent('warning', message, context));
}

export function logError(message: string, context?: Record<string, unknown>): void {
  dispatch(buildEvent('error', message, context));
}

export function logAppError(error: AppError, context?: AppErrorLogContext): void {
  const event: FrontendLogEvent = {
    ts: new Date().toISOString(),
    level: error.level,
    message: error.message,
    source: error.source === 'unknown' ? undefined : error.source,
    route: routeFromLocation(),
    requestId: error.requestId,
    status: error.status,
    errorCode: error.code,
    context: {
      kind: error.kind,
      retryable: error.retryable,
      hint: error.hint,
      ...(error.details !== undefined ? { details: error.details } : {}),
      ...(context ?? {})
    }
  };

  dispatch(event);
}

export function installRuntimeErrorHandlers(onRuntimeError?: (error: AppError) => void): void {
  if (typeof window === 'undefined' || runtimeHandlersInstalled) {
    return;
  }

  runtimeHandlersInstalled = true;

  window.addEventListener('error', (event: ErrorEvent) => {
    const runtimeError = toAppError(event.error ?? event.message, {
      source: 'runtime',
      details: {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      }
    });

    logAppError(runtimeError);
    if (onRuntimeError) {
      onRuntimeError(runtimeError);
    }
  });

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const runtimeError = toAppError(reason, {
      source: 'runtime',
      details: reason
    });

    logAppError(runtimeError);
    if (onRuntimeError) {
      onRuntimeError(runtimeError);
    }
  });
}
