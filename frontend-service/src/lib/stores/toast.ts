import { writable } from 'svelte/store';

// Keep aligned with [`Toaster.svelte`](services/frontend-service/src/lib/components/ui/Toaster.svelte:1)
export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
  persistent?: boolean;
}

function createToastStore() {
  const { subscribe, update } = writable<Toast[]>([]);

  function push(
    type: ToastType,
    message: string,
    options?: {
      timeout?: number;
      persistent?: boolean;
    }
  ): number {
    const id = Date.now();

    update(t => [
      ...t,
      {
        id,
        type,
        message,
        persistent: options?.persistent ?? false
      }
    ]);

    if (!options?.persistent) {
      const timeout = options?.timeout ?? 3000;
      setTimeout(() => remove(id), timeout);
    }

    return id;
  }

  function remove(id: number) {
    update(t => t.filter(toast => toast.id !== id));
  }

  return {
    subscribe,

    /**
     * Generic entrypoint used by some layouts/pages.
     * Compatible with the existing `push()` API.
     */
    show: (t: { type: ToastType; message: string; duration?: number; persistent?: boolean }) =>
      push(t.type, t.message, {
        timeout: t.duration,
        persistent: t.persistent
      }),

    // Standard helpers
    success: (msg: string, timeout?: number) =>
      push('success', msg, { timeout }),

    error: (msg: string, timeout?: number) =>
      push('error', msg, { timeout }),

    warning: (msg: string, timeout?: number) =>
      push('warning', msg, { timeout }),

    info: (msg: string, timeout?: number) =>
      push('info', msg, { timeout }),

    // 🔄 For polling / async operations
    loading: (msg: string) =>
      push('loading', msg, { persistent: true }),

    remove
  };
}

export const toasts = createToastStore();
