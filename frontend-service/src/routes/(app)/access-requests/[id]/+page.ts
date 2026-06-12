import type { PageLoad } from "./$types";
import { getAccessRequestDetails } from "$lib/api/access-requests";

export const load: PageLoad = async ({ fetch, params }) => {
  const request = await getAccessRequestDetails(fetch, params.id);
  return { mode: "dal", request };
};
