import { writable } from 'svelte/store';

// Keep aligned with [`Toaster.svelte`](src/lib/components/ui/Toaster.svelte:1)
export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading';

interface Toast {
  id: number;
  type: ToastType;
  message: string;
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
  const title = defaultTitles[type];
  const clean = message?.trim() || '';
  return `${title} · ${clean}`;
}

function createToastStore() {
  const { subscribe, update } = writable<Toast[]>([]);

  function remove(id: number) {
    update(t => t.filter(toast => toast.id !== id));
  }

  function show(type: ToastType, message: string, duration?: number): number {
    const id = Date.now();

    update(t => [...t, { id, type, message: formatMessage(type, message) }]);
    setTimeout(() => remove(id), duration ?? defaultDuration[type]);

    return id;
  }

  return {
    subscribe,
    show,
    remove,
    success: (message: string, duration?: number) => show('success', message, duration),
    error: (message: string, duration?: number) => show('error', message, duration),
    warning: (message: string, duration?: number) => show('warning', message, duration),
    info: (message: string, duration?: number) => show('info', message, duration),
    loading: (message: string, duration?: number) => show('loading', message, duration)
  };
}

export const toast = createToastStore();
