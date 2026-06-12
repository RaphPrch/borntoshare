import { redirect } from '@sveltejs/kit';

export const load = async (event: { params: { id: string }; parent: () => Promise<{ navigation?: { canSeeStorageRoots?: boolean } }> }) => {
  const parent = await event.parent();
  if (parent?.navigation?.canSeeStorageRoots !== true) {
    throw redirect(302, '/dashboard');
  }
  throw redirect(307, `/storage-roots?selected=${event.params.id}`);
};
