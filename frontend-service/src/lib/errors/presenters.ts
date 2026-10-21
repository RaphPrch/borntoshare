import { t } from '$lib/i18n';
import type { AppError } from './types';

export function presentErrorMessage(error: AppError): string {
  if (error.status === 400) return t('Invalid request.');
  if (error.status === 401) return t('Session expired.');
  if (error.status === 403) return t('Action not allowed.');
  if (error.status === 404) return t('Item not found.');
  if (error.status === 409) return t('Item still used.');
  if ((error.status ?? 0) >= 500) return t('Unexpected error.');
  if (error.kind === 'network') return t('Network error.');
  if (error.kind === 'timeout') return t('Request timeout.');
  return error.message;
}

export function presentErrorHint(error: AppError): string | undefined {
  return error.hint;
}
