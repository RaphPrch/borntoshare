import type { ActivityEvent } from '$lib/api/activity';
import { renderActivity } from './formatter';
import { badgeClass } from './severity';

/**
 * Shared activity formatter used across the app.
 */
export type ActivityCardItem = {
  title: string;
  subtitle1?: string | null;
  subtitle2?: string | null;
  timeLabel?: string | null;
  variant?: 'ok' | 'warn' | 'soft';
  icon?: string;
  // mapped extras consumed by UI cards
  badgeLabel?: string;
  badgeKind?: 'info' | 'admin' | 'critical';
  badgeClass?: string;
};

export function formatActivityItem(ev: ActivityEvent): ActivityCardItem {
  const r = renderActivity(ev as any);

  const outcome = String((ev as any)?.outcome ?? (ev as any)?.result ?? '').toLowerCase();
  const variant: ActivityCardItem['variant'] =
    r.badge.kind === 'critical' ? 'warn' :
    r.badge.kind === 'admin' ? 'warn' :
    outcome === 'success' ? 'ok' : 'soft';

  return {
    title: r.title,
    subtitle1: r.description,
    variant,
    icon: r.icon,
    badgeLabel: r.badge.label,
    badgeKind: r.badge.kind,
    badgeClass: badgeClass(r.badge.kind)
  };
}
