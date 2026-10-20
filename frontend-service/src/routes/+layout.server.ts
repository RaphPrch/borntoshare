import type { LayoutServerLoad } from './$types';

// Interface language chosen in hooks.server.ts, needed by every page
export const load: LayoutServerLoad = ({ locals }) => ({ locale: locals.locale });
