// src/routes/(app)/admin/advanced-settings/+layout.server.js

import { apiServerGet, apiServerGetData } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

export async function load(event) {
  await requireAuth(event);

  const [loggingResult, namingPolicyResult, advancedResult] = await Promise.allSettled([
    apiServerGet('/auth/admin/logging', event),
    apiServerGetData('/naming-policies/global', event),
    apiServerGetData('/admin/config/advanced', event)
  ]);

  const authLoggingRaw =
    loggingResult.status === 'fulfilled' && loggingResult.value && typeof loggingResult.value === 'object'
      ? loggingResult.value
      : {};
  const namingPolicyGlobal =
    namingPolicyResult.status === 'fulfilled' && namingPolicyResult.value && typeof namingPolicyResult.value === 'object'
      ? namingPolicyResult.value
      : {};
  const authLogging = authLoggingRaw;

  const asOptionalNumber = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  };

  const settings = {
    logging: {
      level: typeof authLogging.level === 'string' ? authLogging.level : 'INFO',
      retentionEnabled:
        typeof authLogging.retentionEnabled === 'boolean'
          ? authLogging.retentionEnabled
          : true,
      retentionDays: asOptionalNumber(authLogging.retentionDays) ?? 180
    },
    governance: {
      minGuardians:
        (advancedResult.status === 'fulfilled' ? asOptionalNumber(advancedResult.value?.governance?.minGuardians) : undefined) ?? 2
    }
  };

  return {
    settings,
    namingPolicyGlobal
  };
}
