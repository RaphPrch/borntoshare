import type { PageServerLoad } from './$types';

import { apiServerGetList } from '$lib/server/api-server';
import type { GovernanceAlert } from '$lib/api/governance-alerts';

export const load: PageServerLoad = async (event) => {
  const alerts = await apiServerGetList<GovernanceAlert>('/governance-alerts?status=all&limit=500', event).catch(() => null);
  return {
    alerts: alerts ?? [],
    loadFailed: alerts === null
  };
};
