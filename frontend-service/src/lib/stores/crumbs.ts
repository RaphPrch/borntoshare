/**
 * The levels a page adds to the breadcrumb of the top bar, after « section › entry »:
 * Storage Intelligence › Explorer › Bordeaux › Rights to review.
 *
 *   $effect(() => setCrumbs([{ label: name, href: `/five-s/explore/${id}` }, { label: t('Report') }]));
 *
 * The effect gives the levels back when the page goes (setCrumbs returns the cleanup).
 */
import { writable } from 'svelte/store';

export type Crumb = { label: string; href?: string };

export const crumbs = writable<Crumb[]>([]);

export function setCrumbs(levels: Crumb[]): () => void {
  crumbs.set(levels.filter((level) => level.label));
  return () => crumbs.set([]);
}
