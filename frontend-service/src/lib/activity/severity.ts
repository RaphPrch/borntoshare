import { t } from '$lib/i18n';
import type { ActivityTemplate } from './templates';

export type Badge = 'info' | 'admin' | 'critical';

export function resolveBadgeLabel(badge: Badge) {
  // Activity/event badges must always be displayed in English.
  if (badge === 'critical') return t('badges.critical', {}, 'en');
  if (badge === 'admin') return t('badges.admin', {}, 'en');
  return t('badges.info', {}, 'en');
}

// If backend provides severity, it wins.
export function badgeFromEvent(ev: any, tpl?: ActivityTemplate): Badge {
  const sev = String(ev?.severity ?? '').toLowerCase();
  if (sev === 'critical' || sev === 'high') return 'critical';
  if (sev === 'warning') return 'admin';
  if (tpl?.badge) return tpl.badge;
  // infer from outcome
  const outcome = String(ev?.outcome ?? ev?.result ?? '').toLowerCase();
  if (outcome === 'failure' || outcome === 'denied') return 'admin';
  return 'info';
}

export function badgeClass(badge: Badge) {
  if (badge === 'critical') return 'b2s-badge b2s-badge--critical';
  if (badge === 'admin') return 'b2s-badge b2s-badge--admin';
  return 'b2s-badge b2s-badge--info';
}
