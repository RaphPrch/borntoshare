import { redirect } from '@sveltejs/kit';

export const load = async (event: { params: { id: string } }) => {
  throw redirect(307, `/storage-roots?selected=${event.params.id}&openGovernance=1&role=guardian`);
};
