const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export const formatDateTime = (value?: string) =>
  value
    ? new Date(value).toLocaleString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    : '—';

export const toBoolean = (value: unknown): boolean | null => {
  if (typeof value === 'boolean') return value;
  if (value === null || value === undefined) return null;
  const raw = String(value).trim().toLowerCase();
  if (!raw) return null;
  if (['1', 'true', 'yes', 'y', 'required', 'enforced', 'enabled'].includes(raw)) return true;
  if (['0', 'false', 'no', 'n', 'disabled'].includes(raw)) return false;
  return null;
};

export const boolLabel = (value: boolean | null, whenTrue: string, whenFalse: string) => {
  if (value === true) return whenTrue;
  if (value === false) return whenFalse;
  return '—';
};

export const firstNonEmpty = (values: any[]) => {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text.length > 0) return value;
  }
  return null;
};

export const displayName = (req: any) =>
  firstNonEmpty([
    req?.requested_for_display,
    req?.requested_principal_display,
    req?.requested_by_name,
    req?.requested_by,
    req?.requested_principal_json?.display_name,
    req?.requested_principal_json?.username,
    req?.requested_principal?.display_name,
    req?.requested_principal?.username,
    req?.subject_id
  ]) ?? '—';

export const storageRootLabel = (req: any) =>
  firstNonEmpty([
    req?.storage_root_name,
    req?.scope_display,
    req?.target_path,
    req?.resource_display,
    req?.resource_id
  ]) ?? '—';

export const accessProfileLabel = (req: any) => {
  const raw = String(
    firstNonEmpty([
      req?.access_profile_name,
      req?.access_profile_label,
      req?.permission,
      Array.isArray(req?.permissions) ? req.permissions[0] : null,
      req?.access_profile_id
    ]) ?? ''
  )
    .trim()
    .toLowerCase();

  if (!raw) return '—';
  if (raw.includes('contribution') || raw.includes('write')) return 'Write (Write NTFS)';
  if (raw.includes('audit') || raw.includes('security')) return 'Audit (Read Security)';
  if (raw.includes('read') || raw.includes('lecture')) return 'Read (Read NTFS)';
  return raw.charAt(0).toUpperCase() + raw.slice(1);
};

export const daysLeft = (req: any) => {
  if (!req?.expires_at) {
    const ttl = Number(req?.ttl_days ?? 0);
    return Number.isFinite(ttl) && ttl > 0 ? ttl : 0;
  }
  const ms = new Date(req.expires_at).getTime() - Date.now();
  return clamp(Math.ceil(ms / (1000 * 60 * 60 * 24)), 0, 999);
};

export const ttlCountdownLabel = (req: any) => {
  const expiresAt = req?.expires_at;
  if (!expiresAt) {
    const days = daysLeft(req);
    return `${days} days, 0 hours, 0 minutes`;
  }

  const remainingMs = new Date(expiresAt).getTime() - Date.now();
  const clampedMs = Math.max(0, remainingMs);
  const totalMinutes = Math.floor(clampedMs / (1000 * 60));
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  return `${days} days, ${hours} hours, ${minutes} minutes`;
};

export const timelinePercent = (req: any) => {
  const ttl = Number(req?.ttl_days ?? 0);
  if (!Number.isFinite(ttl) || ttl <= 0) return 0;
  const left = daysLeft(req);
  return clamp(Math.round((left / ttl) * 100), 0, 100);
};

export const requestEvents = (req: any) => {
  const events: Array<{ title: string; date?: string; success?: boolean }> = [
    {
      title: 'Request created',
      date: req?.created_at,
      success: true
    }
  ];

  const lastProvisioning = (req?.provisioning ?? [])[0];
  if (lastProvisioning) {
    const pStatus = String(lastProvisioning?.status ?? '').toLowerCase();
    const ok = pStatus.includes('success') || pStatus.includes('approved') || pStatus.includes('enforced');
    events.push({
      title: `Capsule executed${ok ? ' — Success' : ''}`,
      date: lastProvisioning?.finished_at ?? lastProvisioning?.updated_at ?? lastProvisioning?.created_at,
      success: ok
    });
  }

  return events;
};

export const requestId = (req: any, fallbackRequest: any = null) =>
  Number(req?.request_id ?? req?.id ?? fallbackRequest?.request_id ?? fallbackRequest?.id ?? 0);

export const storageRootIdFromRequest = (row: any): number | null => {
  const direct = Number(row?.storage_root_id ?? row?.target_id ?? 0);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const rawType = String(row?.target_type ?? row?.scope_type ?? '').trim().toLowerCase();
  if (rawType !== 'storage_root') return null;
  const fallback = Number(row?.resource_id ?? row?.id ?? 0);
  return Number.isFinite(fallback) && fallback > 0 ? fallback : null;
};
