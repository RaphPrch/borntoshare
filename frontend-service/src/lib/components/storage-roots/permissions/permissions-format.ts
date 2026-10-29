import { t } from '$lib/i18n';
import type { AccessLevel, PermissionVia } from '$lib/api/storage-root-permissions';

export const levelLabel = (level: AccessLevel | null | undefined): string =>
  level === 'write' ? t('Modify') : level === 'read' ? t('Read') : t('No access');

/** Time left of an access: days, share of its whole duration, and « soon » under 25 % or 7 days */
export function expiryProgress(start: string | null, end: string) {
  const endMs = new Date(end).getTime();
  const now = Date.now();
  const startMs = start ? new Date(start).getTime() : endMs - 30 * 86_400_000;
  const total = Math.max(endMs - startMs, 86_400_000);
  const left = Math.max(endMs - now, 0);
  const percentLeft = Math.round(Math.min(100, (left / total) * 100));
  const daysLeft = Math.ceil(left / 86_400_000);
  return { daysLeft, percentLeft, soon: percentLeft < 25 || daysLeft <= 7 };
}

/** How a person gets the access, in words */
export function viaLabel(via: PermissionVia): string {
  if (via.kind === 'request') return t('Request {code}', { code: via.code });
  if (via.kind === 'group') return t('Group');
  if (via.kind === 'ad_only') return t('Added in the AD');
  return 'accepted' in via && via.accepted ? t('Accepted gap') : t('Outside BornToShare');
}
