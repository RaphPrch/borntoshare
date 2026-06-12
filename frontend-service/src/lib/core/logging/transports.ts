import type { FrontendLogEvent, FrontendLogLevel, LoggerTransport, SyslogSeverity } from './types';

type TransportHttpOptions = {
  endpoint: string;
  fetcher?: typeof fetch;
};

const env = (import.meta as unknown as { env?: Record<string, unknown> }).env;
const DEV = env?.DEV === true || String(env?.MODE ?? '') === 'development';

export function toSyslogSeverity(level: FrontendLogLevel): SyslogSeverity {
  if (level === 'error') return 'err';
  return level;
}

export function createConsoleTransport(): LoggerTransport {
  return {
    name: 'console',
    send(event: FrontendLogEvent) {
      const payload = {
        ...event,
        syslogSeverity: toSyslogSeverity(event.level)
      };

      if (event.level === 'error') {
        console.error('[frontend-log]', payload);
        return;
      }
      if (event.level === 'warning') {
        console.warn('[frontend-log]', payload);
        return;
      }
      if (event.level === 'info') {
        console.info('[frontend-log]', payload);
        return;
      }
      console.debug('[frontend-log]', payload);
    }
  };
}

export function createHttpTransport(options: TransportHttpOptions): LoggerTransport {
  const endpoint = String(options.endpoint ?? '').trim();
  const fetcher = options.fetcher ?? fetch;

  return {
    name: 'http',
    async send(event: FrontendLogEvent) {
      if (!endpoint) return;

      try {
        await fetcher(endpoint, {
          method: 'POST',
          headers: {
            'content-type': 'application/json'
          },
          body: JSON.stringify({
            ...event,
            syslogSeverity: toSyslogSeverity(event.level)
          })
        });
      } catch {
        if (DEV) {
          console.debug('[frontend-log] http transport unavailable');
        }
      }
    }
  };
}
