export class ApiError extends Error {
  status?: number;
  code?: string;
  requestId?: string;
  details?: unknown;
  transport?: 'http' | 'network' | 'timeout';

  constructor(
    message: string,
    options?: {
      status?: number;
      code?: string;
      requestId?: string;
      details?: unknown;
      transport?: 'http' | 'network' | 'timeout';
    }
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = options?.status;
    this.code = options?.code;
    this.requestId = options?.requestId;
    this.details = options?.details;
    this.transport = options?.transport;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function isGenericHttpMessage(value: string | null): boolean {
  if (!value) return false;
  return ['bad request', 'unprocessable entity', 'internal server error'].includes(value.trim().toLowerCase());
}

function usefulString(value: unknown): string | null {
  const text = asString(value);
  if (!text || isGenericHttpMessage(text)) return null;
  return text;
}

export function normalizeErrorMessage(status: number, payload: unknown, statusText: string): string {
  const payloadRecord = asRecord(payload);

  const nestedError =
    payloadRecord && payloadRecord.error && typeof payloadRecord.error === 'object'
      ? (payloadRecord.error as Record<string, unknown>)
      : null;

  const detailRecord = payloadRecord && typeof payloadRecord.detail === 'object'
    ? (payloadRecord.detail as Record<string, unknown>)
    : null;

  const detailMessage =
    usefulString(detailRecord?.message) ??
    usefulString(detailRecord?.error_code) ??
    usefulString(detailRecord?.hint) ??
    usefulString(payloadRecord?.detail);

  let msg =
    usefulString(nestedError?.message) ||
    usefulString(nestedError?.code) ||
    detailMessage ||
    usefulString(payloadRecord?.message) ||
    usefulString(payloadRecord?.error) ||
    `${status} ${statusText}`;

  if (isGenericHttpMessage(msg)) {
    msg = status === 400
      ? 'The request was rejected by the service. Check the form values and try again.'
      : `Request failed with status ${status}`;
  }

  if (status >= 500 && !asString(nestedError?.message)) {
    msg = 'Internal server error';
  }

  if (status === 401) {
    msg = 'Authentication required';
  } else if (status === 403) {
    msg = 'Access forbidden';
  }

  return String(msg);
}
