import { derived } from 'svelte/store';
import { page } from '$app/stores';

/** The optional modules switched on (Advanced settings › Features), as the layout loaded them */
export const enabledFeatures = derived(page, ($page) => new Set<string>(($page.data as any)?.navigation?.features ?? []));

/** « 5S et hygiène des données »: the 5S, the growth curve, the age of the data, the clutter and the duplicates */
export const fivesEnabled = derived(enabledFeatures, ($features) => $features.has('fives'));

/** « Gouvernance des accès »: access requests, guardians, exposure. Off on an installation for the 5S only */
export const governanceEnabled = derived(enabledFeatures, ($features) => $features.has('governance'));
