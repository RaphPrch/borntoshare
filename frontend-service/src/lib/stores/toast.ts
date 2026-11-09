import { t } from '$lib/i18n';
import { writable } from 'svelte/store';

// Keep aligned with [`Toaster.svelte`](src/lib/components/ui/Toaster.svelte:1)
export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading';

/** A reversible action offers its own way back (« Undo »), for a few seconds */
export type ToastAction = { label: string; run: () => unknown | Promise<unknown> };
export type ToastOptions = number | { duration?: number; action?: ToastAction };

interface Toast {
  id: number;
  type: ToastType;
  message: string;
  action?: ToastAction;
  /** How long it stays (ms): the timer bar of the toast runs for this long */
  duration: number;
}

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
  const title = t(defaultTitles[type]);
  const clean = message?.trim() || '';
  return `${title} · ${clean}`;
}

function createToastStore() {
  const { subscribe, update } = writable<Toast[]>([]);

  let lastId = 0;

  function remove(id: number) {
    update(t => t.filter(toast => toast.id !== id));
  }

  function show(type: ToastType, message: string, options?: ToastOptions): number {
    // Counter, not Date.now(): two toasts in the same millisecond must not share a key
    const id = ++lastId;
    const opts = typeof options === 'number' ? { duration: options } : options ?? {};
    // An action needs the time to be read and used
    const duration = opts.duration ?? (opts.action ? 8000 : defaultDuration[type]);

    update(t => [...t, { id, type, message: formatMessage(type, message), action: opts.action, duration }]);
    setTimeout(() => remove(id), duration);

    return id;
  }

  return {
    subscribe,
    show,
    remove,
    success: (message: string, options?: ToastOptions) => show('success', message, options),
    error: (message: string, options?: ToastOptions) => show('error', message, options),
    warning: (message: string, options?: ToastOptions) => show('warning', message, options),
    info: (message: string, options?: ToastOptions) => show('info', message, options),
    loading: (message: string, options?: ToastOptions) => show('loading', message, options)
  };
}

export const toast = createToastStore();
