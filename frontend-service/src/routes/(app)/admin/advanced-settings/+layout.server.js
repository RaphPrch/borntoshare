// src/routes/(app)/admin/advanced-settings/+layout.server.js

import { apiServerGet, apiServerGetData } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

export async function load(event) {
  await requireAuth(event);

  const [
    advancedResult,
    securityResult,
    loggingResult,
    namingPolicyResult
  ] = await Promise.allSettled([
    apiServerGetData('/admin/config/advanced', event),
    apiServerGetData('/admin/advanced-settings/security', event),
    apiServerGet('/auth/admin/logging', event),
    apiServerGetData('/naming-policies/global', event)
  ]);

  const advancedPayload =
    advancedResult.status === 'fulfilled' && advancedResult.value && typeof advancedResult.value === 'object'
      ? advancedResult.value
      : {};
  const dalSecurity =
    securityResult.status === 'fulfilled' && securityResult.value && typeof securityResult.value === 'object'
      ? securityResult.value
      : {};
  const authLoggingRaw =
    loggingResult.status === 'fulfilled' && loggingResult.value && typeof loggingResult.value === 'object'
      ? loggingResult.value
      : {};
  const namingPolicyGlobal =
    namingPolicyResult.status === 'fulfilled' && namingPolicyResult.value && typeof namingPolicyResult.value === 'object'
      ? namingPolicyResult.value
      : {};
  const advanced = advancedPayload;
  const authLogging = authLoggingRaw;

  const asOptionalNumber = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  };

  const settings = {
    security: {
      enforceStrongPasswords: Boolean(dalSecurity.enable_strong_password),
      passwordMinLength: asOptionalNumber(dalSecurity.password_min_length) ?? 10,
      passwordHistory: asOptionalNumber(dalSecurity.password_history) ?? 5,
      passwordExpiryDays: asOptionalNumber(dalSecurity.password_expiry_days) ?? 90
    },
    logging: {
      level: typeof authLogging.level === 'string' ? authLogging.level : 'INFO',
      retentionEnabled:
        typeof authLogging.retentionEnabled === 'boolean'
          ? authLogging.retentionEnabled
          : true,
      retentionDays: asOptionalNumber(authLogging.retentionDays) ?? 180
    },
    maintenance:
      advanced?.maintenance && typeof advanced.maintenance === 'object'
        ? advanced.maintenance
        : {
            enabled: false,
            message: 'Le système est en cours de maintenance, merci de réessayer plus tard.',
            allowedCidrs: ['10.0.0.0/24', '192.168.5.0/24']
          }
  };

  return {
    settings,
    namingPolicyGlobal
  };
}
