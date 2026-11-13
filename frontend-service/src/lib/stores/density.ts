import { writable } from 'svelte/store';

/**
 * Display density: « comfortable » (default) or « compact » (tighter rows, tiles and margins, more lines on screen).
 * Kept in a cookie so the server writes it on <html> before the first paint (hooks.server.ts).
 */
export type Density = 'comfortable' | 'compact';

function current(): Density {
  if (typeof document === 'undefined') return 'comfortable';
  return document.documentElement.dataset.density === 'compact' ? 'compact' : 'comfortable';
}

const store = writable<Density>(current());

export const density = {
  subscribe: store.subscribe,
  set(value: Density) {
    store.set(value);
    if (typeof document === 'undefined') return;
    document.documentElement.dataset.density = value;
    document.cookie = `b2s_density=${value}; path=/; max-age=31536000; samesite=lax`;
  },
  toggle() {
    density.set(current() === 'compact' ? 'comfortable' : 'compact');
  },
  /** Reads the value the server wrote on <html> (after hydration) */
  sync() {
    store.set(current());
  }
};
