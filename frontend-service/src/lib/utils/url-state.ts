/**
 * Filters and tabs kept in the address: a link copied opens the same view, Back finds it again.
 *
 *   let filter = $state(readParam('filter', 'todo'));
 *   $effect(() => writeParams({ filter: filter === 'todo' ? null : filter }));
 */
import { browser } from '$app/environment';
import { goto } from '$app/navigation';

/** The value of a parameter of the current address (on the server and before hydration: the fallback). */
export function readParam<T extends string>(name: string, fallback: T, allowed?: readonly T[]): T {
  if (!browser) return fallback;
  const value = new URL(window.location.href).searchParams.get(name);
  if (value == null || value === '') return fallback;
  return (allowed && !allowed.includes(value as T) ? fallback : value) as T;
}

/** Writes these parameters (null or '' removes one) without a new entry in the history nor a scroll. */
export function writeParams(values: Record<string, string | number | null | undefined>): void {
  if (!browser) return;
  const url = new URL(window.location.href);
  for (const [name, value] of Object.entries(values)) {
    if (value == null || value === '') url.searchParams.delete(name);
    else url.searchParams.set(name, String(value));
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  if (next !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    void goto(next, { replaceState: true, keepFocus: true, noScroll: true });
  }
}
