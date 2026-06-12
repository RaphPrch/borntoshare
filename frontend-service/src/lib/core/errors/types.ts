export type ErrorKind =
  | 'network'
  | 'timeout'
  | 'auth'
  | 'forbidden'
  | 'validation'
  | 'not_found'
  | 'conflict'
  | 'backend'
  | 'unknown';

export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

export type ErrorSource = 'http' | 'ui' | 'runtime' | 'auth' | 'ssr' | 'unknown';

export type AppError = {
  message: string;
  kind: ErrorKind;
  level: LogLevel;
  status?: number;
  code?: string;
  requestId?: string;
  hint?: string;
  retryable: boolean;
  details?: unknown;
  source: ErrorSource;
};

