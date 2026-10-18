import { logError, logInfo, logWarning } from './logger';

type UiActivityLevel = 'info' | 'warning' | 'error';

type UiLogLevel = UiActivityLevel;

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
