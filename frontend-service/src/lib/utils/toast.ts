import { toasts } from '../stores/toast';

type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading';

const defaultDuration: Record<ToastType, number> = {
  success: 3000,
  error: 4500,
  warning: 4000,
  info: 3000,
  loading: 6000
};

const defaultTitles: Record<ToastType, string> = {
  success: 'Success',
  error: 'Error',
  warning: 'Warning',
  info: 'Info',
  loading: 'Loading'
};

function formatMessage(type: ToastType, message: string) {
  const title = defaultTitles[type];
  const clean = message?.trim() || '';
  return `${title} · ${clean}`;
}

export const toast = {
  show: (type: ToastType, message: string, duration?: number) =>
    toasts.show({
      type,
      message: formatMessage(type, message),
      duration: duration ?? defaultDuration[type]
    }),
  success: (message: string, duration?: number) =>
    toast.show('success', message, duration),
  error: (message: string, duration?: number) =>
    toast.show('error', message, duration),
  warning: (message: string, duration?: number) =>
    toast.show('warning', message, duration),
  info: (message: string, duration?: number) =>
    toast.show('info', message, duration),
  loading: (message: string, duration?: number) =>
    toast.show('loading', message, duration)
};
