import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

/** The Assistant was at /pilot: old links and bookmarks keep working, their question (?q=…) with them. */
export const GET: RequestHandler = ({ url }) => {
  throw redirect(308, `/assistant${url.search}`);
};
