import { t } from '$lib/i18n';
import type { StatusVariant } from '$lib/utils/status';
import type { HealthStatus, InfraComponent } from '$lib/api/infrastructure';

export const STATUS_VARIANT: Record<HealthStatus, StatusVariant> = {
  healthy: 'success',
  degraded: 'warning',
  down: 'error',
  unknown: 'muted'
};

export function statusLabel(status: HealthStatus | null | undefined): string {
  if (status === 'healthy') return t('Operational');
  if (status === 'degraded') return t('Degraded');
  if (status === 'down') return t('Down');
  return t('Unknown');
}

/** Display order and names of the component groups */
export const CATEGORIES: { key: string; label: () => string; icon: string }[] = [
  { key: 'web', label: () => t('Web'), icon: 'bi-window' },
  { key: 'service', label: () => t('Platform services'), icon: 'bi-hdd-stack' },
  { key: 'data', label: () => t('Databases'), icon: 'bi-database' },
  { key: 'queue', label: () => t('Job queue'), icon: 'bi-stack' },
  { key: 'worker', label: () => t('Workers'), icon: 'bi-cpu' },
  { key: 'security', label: () => t('Security and SSO'), icon: 'bi-shield-lock' },
  { key: 'directory', label: () => t('Directories'), icon: 'bi-diagram-3' },
  { key: 'storage', label: () => t('File servers'), icon: 'bi-folder2-open' },
  { key: 'custom', label: () => t('Other components'), icon: 'bi-box' }
];

export function groupComponents(components: InfraComponent[]): { key: string; label: string; icon: string; items: InfraComponent[] }[] {
  const known = new Set(CATEGORIES.map((c) => c.key));
  return CATEGORIES.map((category) => ({
    key: category.key,
    label: category.label(),
    icon: category.icon,
    items: components.filter((c) => (known.has(c.category) ? c.category : 'custom') === category.key)
  })).filter((group) => group.items.length > 0);
}

/** Worst state of a list: one component down makes the group down */
export function worstStatus(items: { status: HealthStatus }[]): HealthStatus {
  const rank: Record<HealthStatus, number> = { down: 3, degraded: 2, unknown: 1, healthy: 0 };
  return items.reduce<HealthStatus>((worst, item) => (rank[item.status] > rank[worst] ? item.status : worst), 'healthy');
}

export const HEALTH_INTERVALS = [1, 2, 5, 10, 15, 30, 60];
export const SYNC_INTERVALS = [60, 120, 180, 360, 720, 1440];

export function intervalLabel(minutes: number): string {
  if (minutes % 1440 === 0) return minutes === 1440 ? t('Every day') : t('Every {n} days', { n: minutes / 1440 });
  if (minutes % 60 === 0) return minutes === 60 ? t('Every hour') : t('Every {n} hours', { n: minutes / 60 });
  return minutes === 1 ? t('Every minute') : t('Every {n} minutes', { n: minutes });
}

export function formatDuration(seconds: number | null | undefined): string {
  const s = Number(seconds ?? 0);
  if (!Number.isFinite(s) || s <= 0) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} ${t('d')} ${h} ${t('h')}`;
  if (h > 0) return `${h} ${t('h')} ${m} ${t('min')}`;
  return `${m} ${t('min')}`;
}
