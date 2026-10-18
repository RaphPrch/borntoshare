import type { AppError } from './types';

export function presentErrorMessage(error: AppError): string {
  if (error.status === 400) return 'Invalid request.';
  if (error.status === 401) return 'Session expired.';
  if (error.status === 403) return 'Action not allowed.';
  if (error.status === 404) return 'Item not found.';
  if (error.status === 409) return 'Item still used.';
  if ((error.status ?? 0) >= 500) return 'Unexpected error.';
  if (error.kind === 'network') return 'Network error.';
  if (error.kind === 'timeout') return 'Request timeout.';
  return error.message;
}

export function presentErrorHint(error: AppError): string | undefined {
  return error.hint;
}
