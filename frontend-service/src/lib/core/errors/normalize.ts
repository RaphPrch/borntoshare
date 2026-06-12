import { ApiError } from '../../http/errors';

import type { AppError, ErrorKind, LogLevel } from './types';

type ApiErrorLike = {
  name: 'ApiError';
  message: string;
  status?: number;
  code?: string;
  requestId?: string;
  request_id?: string;
  details?: unknown;
  transport?: 'http' | 'network' | 'timeout';
};

type ErrorDefaults = {
  level: LogLevel;
  retryable: boolean;
  hint?: string;
};

const DEFAULT_HINTS: Record<ErrorKind, string | undefined> = {
  network: 'Check your network connectivity and try again.',
  timeout: 'The service is taking too long to respond. Please try again shortly.',
  auth: 'Your session appears expired. Sign in again and retry.',
  forbidden: 'You do not have the required permissions for this action.',
  validation: 'Some data is invalid. Check fields and try again.',
  not_found: 'The requested resource was not found. Refresh the page.',
  conflict: 'A state conflict was detected. Refresh and retry.',
  backend: 'Backend is unavailable or failing. Try again later.',
  unknown: 'Une erreur inattendue est survenue.'
};

const DEFAULT_MESSAGES: Record<ErrorKind, string> = {
  network: 'Network error',
  timeout: 'Request timeout',
  auth: 'Authentication required',
  forbidden: 'Access forbidden',
  validation: 'Validation failed',
  not_found: 'Resource not found',
  conflict: 'Conflict detected',
  backend: 'Backend error',
  unknown: 'Unexpected error'
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function isApiErrorLike(value: unknown): value is ApiErrorLike {
  const rec = asRecord(value);
  if (!rec) return false;
  return rec.name === 'ApiError' && typeof rec.message === 'string';
}

function asNumber(value: unknown): number | undefined {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
}

function asString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function extractStatus(record: Record<string, unknown> | null): number | undefined {
  if (!record) return undefined;
  return asNumber(record.status);
}

function extractCode(record: Record<string, unknown> | null): string | undefined {
  if (!record) return undefined;
  return asString(record.code) ?? asString(record.error_code);
}

function extractRequestId(record: Record<string, unknown> | null): string | undefined {
  if (!record) return undefined;
  return (
    asString(record.requestId) ??
    asString(record.request_id) ??
    asString(record.requestID) ??
    asString(record['x-request-id'])
  );
}

function extractMessageFromPayload(payload: unknown): string | undefined {
  const rec = asRecord(payload);
  if (!rec) {
    return asString(payload);
  }

  const nestedError = asRecord(rec.error);
  const nestedDetail = asRecord(rec.detail);

  return (
    asString(rec.message) ??
    asString(rec.error) ??
    asString(rec.detail) ??
    asString(nestedError?.message) ??
    asString(nestedError?.code) ??
    asString(nestedDetail?.message) ??
    asString(nestedDetail?.hint)
  );
}

function defaultsForKind(kind: ErrorKind): ErrorDefaults {
  switch (kind) {
    case 'network':
    case 'timeout':
      return { level: 'warning', retryable: true, hint: DEFAULT_HINTS[kind] };
    case 'auth':
    case 'forbidden':
    case 'validation':
      return { level: 'warning', retryable: false, hint: DEFAULT_HINTS[kind] };
    case 'not_found':
    case 'conflict':
      return { level: 'warning', retryable: true, hint: DEFAULT_HINTS[kind] };
    case 'backend':
      return { level: 'error', retryable: true, hint: DEFAULT_HINTS[kind] };
    default:
      return { level: 'error', retryable: false, hint: DEFAULT_HINTS.unknown };
  }
}

function kindFromStatus(status?: number): ErrorKind | null {
  if (status === undefined) return null;
  if (status === 401) return 'auth';
  if (status === 403) return 'forbidden';
  if (status === 400 || status === 422) return 'validation';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status >= 500) return 'backend';
  return null;
}

function isTimeoutLike(error: Error, code?: string): boolean {
  if (code === 'REQUEST_TIMEOUT') return true;
  return error.name === 'AbortError' || /timeout/i.test(error.message);
}

function isNetworkLike(error: Error, code?: string): boolean {
  if (code === 'NETWORK_ERROR') return true;
  return /network|failed to fetch|load failed/i.test(error.message);
}

function mergeWithContext(base: AppError, context?: Partial<AppError>): AppError {
  if (!context) return base;

  const merged: AppError = {
    ...base,
    ...context
  };

  const defaults = defaultsForKind(merged.kind);

  if (context.level === undefined) {
    merged.level = defaults.level;
  }
  if (context.retryable === undefined) {
    merged.retryable = defaults.retryable;
  }
  if (context.hint === undefined) {
    merged.hint = merged.hint ?? defaults.hint;
  }

  if (!merged.message?.trim()) {
    merged.message = DEFAULT_MESSAGES[merged.kind];
  }

  return merged;
}

export function toAppError(error: unknown, context?: Partial<AppError>): AppError {
  const initialSource = context?.source ?? 'unknown';

  if (
    error &&
    typeof error === 'object' &&
    'kind' in error &&
    'level' in error &&
    'retryable' in error &&
    'message' in error
  ) {
    return mergeWithContext(error as AppError, context);
  }

  let kind: ErrorKind = 'unknown';
  let status: number | undefined;
  let code: string | undefined;
  let requestId: string | undefined;
  let details: unknown = undefined;
  let message: string | undefined;

  if (isApiErrorLike(error)) {
    const apiError = error;
    status = apiError.status;
    code = apiError.code;
    requestId = apiError.requestId ?? apiError.request_id;
    details = apiError.details;
    message = extractMessageFromPayload(apiError.details) ?? apiError.message;

    if (apiError.transport === 'timeout') {
      kind = 'timeout';
    } else if (apiError.transport === 'network') {
      kind = 'network';
    }
  } else if (error instanceof Error) {
    message = error.message;
    const rec = asRecord(error);
    status = extractStatus(rec);
    code = extractCode(rec);
    requestId = extractRequestId(rec);
    details = rec?.details ?? rec?.detail;

    if (isTimeoutLike(error, code)) {
      kind = 'timeout';
    } else if (isNetworkLike(error, code)) {
      kind = 'network';
    }
  } else {
    const rec = asRecord(error);
    status = extractStatus(rec);
    code = extractCode(rec);
    requestId = extractRequestId(rec);
    details = rec?.details ?? rec?.detail;
    message = extractMessageFromPayload(error);
  }

  if (kind === 'unknown') {
    const byStatus = kindFromStatus(status);
    if (byStatus) {
      kind = byStatus;
    }
  }

  const defaults = defaultsForKind(kind);

  const base: AppError = {
    message: message?.trim() || DEFAULT_MESSAGES[kind],
    kind,
    level: defaults.level,
    status,
    code,
    requestId,
    hint: defaults.hint,
    retryable: defaults.retryable,
    details,
    source: initialSource
  };

  return mergeWithContext(base, context);
}
