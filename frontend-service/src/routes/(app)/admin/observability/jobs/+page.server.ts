import type { PageServerLoad } from './$types';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

type AdminJobRow = {
  id: number;
  correlation_id?: string | null;
  job_type?: string | null;
  action?: string | null;
  status?: string | null;
  identity_source_id?: number | null;
  storage_root_access_profile_id?: number | null;
  queue_age_seconds?: number | null;
  watchdog_republish_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const jobs = await apiServerGetList<AdminJobRow>('/admin/jobs?limit=200', event);

  return {
    initialJobs: jobs,
    generatedAt: new Date().toISOString()
  };
};

