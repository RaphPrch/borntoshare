import { toAppError, type AppError } from '$lib/core/errors';
import { toast } from '$lib/utils/toast';

const STATUS_MESSAGES: Record<number, string> = {
  400: 'Invalid request.',
  401: 'Session expired.',
  403: 'Action not allowed.',
  404: 'Item not found.',
  409: 'Item still used.',
  500: 'Unexpected error.'
};

function messageForError(error: AppError, fallback = 'Unexpected error.'): string {
  if (error.status && STATUS_MESSAGES[error.status]) {
    return STATUS_MESSAGES[error.status];
  }
  if (error.kind === 'network') return 'Network error.';
  if (error.kind === 'timeout') return 'Request timeout.';
  return fallback;
}

export function showApiErrorToast(error: unknown, fallback?: string): AppError {
  const appError = toAppError(error, { source: 'ui' });
  toast.error(messageForError(appError, fallback));
  return appError;
}
