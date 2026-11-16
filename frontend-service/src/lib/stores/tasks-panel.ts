import { writable } from 'svelte/store';

/** The recent tasks bar at the bottom of the page: unfolded or not (the button of the top bar toggles it too). */
export const tasksPanelOpen = writable(false);
