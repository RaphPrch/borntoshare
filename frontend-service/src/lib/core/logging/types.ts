import type { AppError } from '../errors/types';

export type FrontendLogLevel = 'debug' | 'info' | 'warning' | 'error';

export type FrontendLogSource = 'ui' | 'http' | 'runtime' | 'auth' | 'ssr';

export type FrontendLogEvent = {
  ts: string;
  level: FrontendLogLevel;
  message: string;
  route?: string;
  action?: string;
  requestId?: string;
  status?: number;
  errorCode?: string;
  source?: FrontendLogSource;
  context?: Record<string, unknown>;
};

export type LoggerTransport = {
  name: string;
  send: (event: FrontendLogEvent) => void | Promise<void>;
};

export type SyslogSeverity = 'debug' | 'info' | 'warning' | 'err';

export type AppErrorLogContext = Record<string, unknown>;

export type AppErrorLike = Pick<AppError, 'message' | 'level' | 'status' | 'code' | 'requestId' | 'source'>;

