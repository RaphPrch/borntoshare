import { beforeNavigate, goto } from '$app/navigation';
import { onDestroy } from 'svelte';
import { writable } from 'svelte/store';

/**
 * A form with unsaved edits asks before the page is left: a link, the back button or the menu open the app's
 * dialog (rendered once by the layout); closing the tab gets the browser's own question.
 * Call `guardUnsaved(() => dirty)` while the component initialises.
 */
export const unsavedPrompt = writable<{ open: boolean; discard: (() => void) | null }>({ open: false, discard: null });

let bypass = false;

export function guardUnsaved(isDirty: () => boolean): void {
  beforeNavigate((navigation) => {
    if (bypass || !isDirty()) return;
    if (navigation.type === 'leave') {
      navigation.cancel(); // the browser asks « Leave the site? »
      return;
    }
    const to = navigation.to?.url;
    navigation.cancel();
    if (!to) return;
    unsavedPrompt.set({
      open: true,
      discard: () => {
        unsavedPrompt.set({ open: false, discard: null });
        bypass = true;
        void goto(to).finally(() => (bypass = false));
      }
    });
  });
  onDestroy(() => unsavedPrompt.set({ open: false, discard: null }));
}
