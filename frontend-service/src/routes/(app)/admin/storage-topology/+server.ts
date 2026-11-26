import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

// The storage topology is a tab of Insights & Recommendations now: the old address keeps working
export const GET: RequestHandler = ({ url }) => {
  throw redirect(308, `/insights/topology${url.search}`);
};
