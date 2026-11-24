import type { PageServerLoad } from './$types';
import { fivesOff } from '$lib/server/fives-off';

/** A report of the 5S module (fives-…) while the module is not usable: the page says why instead of calling it */
export const load: PageServerLoad = async (event) => {
  if (!event.params.kind.startsWith('fives-')) return { fivesOff: null };
  const { navigation, me } = await event.parent();
  return { fivesOff: await fivesOff(event, { features: navigation?.features, isAdmin: me?.is_admin === true }) };
};
