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
  apiPutData,
  type FetchLike
} from './client';

// -----------------------
// Types
// -----------------------

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
export type CookieSameSite = 'Lax' | 'Strict' | 'None';

export type SecurityConfig = {
  enforceStrongPasswords: boolean;
  passwordMinLength: number;
  passwordHistory: number;
  passwordExpiryDays: number;
};

type SecuritySettingsDal = {
  enable_strong_password?: boolean;
  password_min_length?: number;
  password_history?: number;
  password_expiry_days?: number;
};

export type LoggingConfig = {
  level: LogLevel;
  retentionEnabled?: boolean;
  retentionDays?: number;
};

export type MaintenanceConfig = {
  enabled: boolean;
  message: string;
  allowedCidrs: string[];
};

export type ActionResult = {
  ok: boolean;
  message?: string;
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
};

export async function purgeLogs(fetchFn: FetchLike) {
  return apiPost<ActionResult>(fetchFn, '/auth/admin/logs/purge', {});
}

export async function saveSecurityConfig(fetchFn: FetchLike, security: SecurityConfig) {
  const payload: SecuritySettingsDal = {
    enable_strong_password: security.enforceStrongPasswords,
    password_min_length: security.passwordMinLength,
    password_history: security.passwordHistory,
    password_expiry_days: security.passwordExpiryDays
  };
  return apiPutData<ActionResult>(fetchFn, '/admin/advanced-settings/security', payload);
}

export async function saveLoggingConfig(fetchFn: FetchLike, logging: LoggingConfig) {
  const payload = {
    level: logging.level,
    retentionEnabled: logging.retentionEnabled ?? true,
    retentionDays: logging.retentionDays ?? 180
  };
  return apiPut<ActionResult>(fetchFn, '/auth/admin/logging', payload);
}

export async function saveMaintenanceConfig(fetchFn: FetchLike, maintenance: MaintenanceConfig) {
  return apiPostData<ActionResult>(fetchFn, '/admin/config/advanced', { maintenance });
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
