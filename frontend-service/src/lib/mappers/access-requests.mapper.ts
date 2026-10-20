import { t } from '$lib/i18n';
const firstNonEmpty = (values: any[]) => {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text.length > 0) return value;
  }
  return null;
};

export const accessRequestId = (row: any): number =>
  Number(row?.request_id ?? row?.id ?? 0);

export const accessRequestTargetLabel = (row: any): string =>
  String(
    firstNonEmpty([
      row?.storage_root_name,
      row?.scope_display,
      row?.target_path,
      row?.resource_display,
      row?.resource_id
    ]) ?? '—'
  );

export const accessRequestTargetPath = (row: any): string =>
  String(
    firstNonEmpty([
      row?.scope_type,
      row?.target_type,
      row?.resource_type
    ]) ?? '—'
  );

export const accessRequestRequesterName = (row: any): string =>
  String(
    firstNonEmpty([
      row?.requested_for_display,
      row?.requested_principal_display,
      row?.requested_by_name,
      row?.requested_by,
      row?.requested_principal_json?.display_name,
      row?.requested_principal_json?.username,
      row?.requested_principal?.display_name,
      row?.requested_principal?.username,
      row?.subject_id
    ]) ?? '—'
  );

export const accessRequestAccessLabel = (row: any): string => {
  const raw = String(
    firstNonEmpty([
      row?.access_profile_name,
      row?.access_profile_label,
      row?.permission,
      Array.isArray(row?.permissions) ? row.permissions[0] : null
    ]) ?? ''
  )
    .trim()
    .toLowerCase();

  if (!raw) return '—';
  if (raw.includes('contribution') || raw.includes('write')) return t('Write (Write NTFS)');
  if (raw.includes('audit') || raw.includes('security')) return t('Audit (Read Security)');
  if (raw.includes('read') || raw.includes('lecture')) return t('Read (Read NTFS)');
  return raw.charAt(0).toUpperCase() + raw.slice(1);
};
