import { toast } from '../../stores/toast';

import { presentErrorMessage } from './presenters';
import type { AppError } from './types';

export function notifyError(error: AppError): void {
  toast.error(presentErrorMessage(error));
}
