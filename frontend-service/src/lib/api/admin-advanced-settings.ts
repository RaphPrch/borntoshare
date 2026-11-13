// src/lib/api/admin-advanced-settings.ts
// Contracts for the Advanced Settings (config + runtime actions).
//
// V1 strict: fail-fast on non-conforming responses.

import {
  apiDelete,
  apiGet,
  apiGetData,
  apiPost,
  apiPostData,
  apiPut,
  type FetchLike
} from './client';

// -----------------------
// Types
// -----------------------

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
type LoggingConfig = {
  level: LogLevel;
  retentionEnabled?: boolean;
  retentionDays?: number;
};

type ActionResult = {
  ok: boolean;
  message?: string;
  // Purge of old logs
  retention_days?: number;
  audit_events?: number;
  health_events?: number;
  // Optional async job fields
  job_id?: string;
  status_url?: string;
};

export type UserSession = {
  id: string;
  user: string;
  roles: string[];
  status: 'active' | 'expired' | 'revoked';
  created_at: string;
  last_seen: string;
  auth_source?: string;
  is_admin?: boolean;
  is_current?: boolean;
};

export async function purgeLogs(fetchFn: FetchLike) {
  return apiPost<ActionResult>(fetchFn, '/auth/admin/logs/purge', {});
}

export async function saveSessionLimits(fetchFn: FetchLike, ttlSeconds: number, idleSeconds: number) {
  return apiPost<ActionResult>(fetchFn, '/admin/config/advanced', { sessions: { ttlSeconds, idleSeconds } });
}

export type DnsDomain = { domain: string; servers: string[]; origin?: string; source?: string };

/** DNS servers of the Windows domains, used by the worker (Advanced settings > Network and DNS) */
export async function saveDnsDomains(fetchFn: FetchLike, dns: DnsDomain[]) {
  return apiPost<ActionResult>(fetchFn, '/admin/config/advanced', {
    network: { dns: dns.map(({ domain, servers }) => ({ domain, servers })) }
  });
}

/** First step of the setup: the access governance, the 5S (licensed), or both */
export async function chooseSetupModules(fetchFn: FetchLike, modules: { governance: boolean; fives: boolean }) {
  return apiPost<ActionResult>(fetchFn, '/admin/setup/modules', modules);
}

/** Start without LDAP / OpenLDAP directory: local accounts only, the directory is added later (Directories) */
export async function skipSetupDirectory(fetchFn: FetchLike) {
  return apiPost<ActionResult>(fetchFn, '/admin/setup/skip-directory', {});
}

export async function completeSetup(fetchFn: FetchLike) {
  return apiPost<ActionResult>(fetchFn, '/admin/setup/complete', {});
}

export async function saveLoggingConfig(fetchFn: FetchLike, logging: LoggingConfig) {
  const payload = {
    level: logging.level,
    retentionEnabled: logging.retentionEnabled ?? true,
    retentionDays: logging.retentionDays ?? 180
  };
  return apiPut<ActionResult>(fetchFn, '/auth/admin/logging', payload);
}

// -----------------------
// User sessions (admin)
// -----------------------

export async function listUserSessions(fetchFn: FetchLike) {
  return apiGet<{ sessions: UserSession[] }>(
    fetchFn,
    '/auth/admin/sessions'
  );
}

export async function revokeUserSession(fetchFn: FetchLike, sessionId: string) {
  return apiDelete<ActionResult>(fetchFn, `/auth/admin/sessions/${sessionId}`);
}

/** Saves one or several sections of Advanced settings (merged into the stored ones by core-service). */
export async function saveAdvancedSections(fetchFn: FetchLike, sections: Record<string, unknown>) {
  return apiPost<ActionResult>(fetchFn, '/admin/config/advanced', sections);
}

export async function sendTestEmail(fetchFn: FetchLike, to: string) {
  return apiPostData<{ ok: boolean; error?: string }>(fetchFn, '/admin/config/notifications/test', { to });
}

export type PublicSettings = {
  requests: { durations: number[]; allowPermanent: boolean; maxDays: number; minReasonLength: number };
  banner: { enabled: boolean; message: string; tone: 'info' | 'warning' | 'danger' };
};

export async function getPublicSettings(fetchFn: FetchLike) {
  return apiGetData<PublicSettings>(fetchFn, '/admin/config/public');
}

