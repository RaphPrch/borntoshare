import { toasts } from '../../stores/toast';

import { presentErrorMessage } from './presenters';
import type { AppError } from './types';

export function notifyError(error: AppError): void {
  toasts.error(presentErrorMessage(error));
}

export function notifySuccess(message: string): void {
  toasts.success(message);
}

export function notifyInfo(message: string): void {
  toasts.info(message);
}

export function notifyWarning(message: string): void {
  toasts.warning(message);
}
