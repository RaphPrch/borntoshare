import type { LayoutServerLoad } from './$types';
import { fivesOff } from '$lib/server/fives-off';

/**
 * The 5S screens exist only while the module is usable: licensed, switched on and answering. Otherwise none of them
 * loads (no endless skeleton, no failing call): the layout says why, and an administrator gets the way to fix it.
 */
export const load: LayoutServerLoad = async (event) => {
  const { navigation, me } = await event.parent();
  return { fivesOff: await fivesOff(event, { features: navigation?.features, isAdmin: me?.is_admin === true }) };
};
