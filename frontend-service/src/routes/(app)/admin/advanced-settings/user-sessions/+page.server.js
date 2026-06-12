import { requireAuth } from '$lib/utils/requireAuth.server';
import { apiServerGet } from '$lib/server/api-server';

export const load = async (event) => {
  await requireAuth(event);

  const sessionsPayload = await apiServerGet('/auth/admin/sessions', event);

  return {
    sessions: Array.isArray(sessionsPayload?.sessions) ? sessionsPayload.sessions : []
  };
};
