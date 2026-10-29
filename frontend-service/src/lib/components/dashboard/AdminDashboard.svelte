<script lang="ts">
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import { formatDateTime } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import DashboardShell from './DashboardShell.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { formatActivityItem } from '$lib/activity/format';
  import RequestsActivityChart from './RequestsActivityChart.svelte';

  // Expected (safe) shape:
  // data.stats: { storage_roots, storage_endpoints, admins, pending_requests }
  // data.activities: [{ action, target_type, target_name, created_at, actor_display_name }]
  export let data: any;

  const stats = data?.stats ?? data?.summary ?? {};
  // Sign-ins are frequent and say little about platform changes: keep them out of this card
  const activities = (Array.isArray(data?.activities) ? data.activities : []).filter(
    (a: any) => String(a?.action ?? '') !== 'auth.login'
  );
  const requestsSeries = Array.isArray(stats?.requests_last_30_days) ? stats.requests_last_30_days : [];

  const attention = [
    {
      key: 'open_alerts_count',
      label: t('Open alerts'),
      hint: t('{count} critical or high', { count: Number(stats?.critical_alerts_count ?? 0) }),
      href: '/observability?tab=alerts&severity=critical_high',
      icon: 'bi-exclamation-octagon',
      tone: 'danger'
    },
    { key: 'failed_jobs_24h_count', label: t('Failed jobs (24 h)'), hint: null, href: '/observability?tab=jobs&status=FAILED', icon: 'bi-x-octagon', tone: 'warning' },
    {
      key: 'stale_pending_requests_count',
      label: t('Requests waiting for more than 3 days'),
      hint: null,
      href: '/access-requests',
      icon: 'bi-hourglass-bottom',
      tone: 'warning'
    }
  ] as const;

  const kpi = [
    { key: 'storage_roots', label: t('Storage Roots'), href: '/storage-roots', icon: 'bi-folder2-open', tone: 'info' },
    { key: 'storage_endpoints', label: t('Storage Endpoints'), href: '/admin/storage-endpoints', icon: 'bi-hdd-network', tone: 'info' },
    { key: 'admins', label: t('Admins'), href: '/admin/identity', icon: 'bi-person-gear', tone: 'info' },
    { key: 'pending_requests', label: t('Pending Requests'), href: '/access-requests', icon: 'bi-hourglass-split', tone: 'warning' }
  ] as const;

  const num = (v: any) => (Number.isFinite(Number(v)) ? Number(v) : 0);

  const timeLabel = (value: unknown): string => {
    return formatDateTime(value);
  };
</script>

<DashboardShell title={t('Admin Dashboard')} subtitle={t('Platform Operations Overview')}>
  <div class="b2s-kpi-grid">
    {#each kpi as item}
      <KpiCard label={item.label} value={num(stats[item.key])} icon={item.icon} tone={item.tone} href={item.href} />
    {/each}
  </div>

  <section class="dashboard-attention" aria-labelledby="dashboard-attention-title">
    <h2 id="dashboard-attention-title">{t('Needs attention')}</h2>
    <div class="b2s-kpi-grid">
      {#each attention as item}
        <KpiCard
          label={item.label}
          value={num(stats[item.key])}
          hint={item.hint}
          icon={num(stats[item.key]) > 0 ? item.icon : 'bi-check2-circle'}
          tone={num(stats[item.key]) > 0 ? item.tone : 'success'}
          href={item.href}
        />
      {/each}
    </div>
  </section>

  <div class="dashboard-columns">
  <RequestsActivityChart series={requestsSeries} />

  <section class="panel">
    <div class="panel__header">
      <h2>{t('Latest admin activity')}</h2>
      <div class="panel__hint">{t('Recent actions across the platform')}</div>
    </div>

    {#if activities.length === 0}
      <EmptyStateInline message={t('No recent activity.')} />
    {:else}
      <ul class="activity">
        {#each activities.slice(0, 8) as a}
          {@const rendered = formatActivityItem(a)}
          <li>
            <div class="activity__main">
              <span class="activity__action">{rendered.title ?? t('Event')}</span>
              <span class="activity__target">
                {rendered.subtitle1 ?? ((a.target_type ?? 'target') + (a.target_name ? ` • ${a.target_name}` : ''))}
              </span>
            </div>
            <div class="activity__meta">
              <span>{a.actor_display_name ?? a.actor_display ?? (a.actor_type === 'system' ? t('System') : a.actor_id ?? '—')}</span>
              <span class="dot">•</span>
              <span>{timeLabel(a.created_at)}</span>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
  </div>
</DashboardShell>

<style>
  .dashboard-attention h2 {
    margin: 8px 0 12px;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-lg);
    font-weight: 600;
  }

  .dashboard-columns {
    display: grid;
    grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
    gap: 16px;
    align-items: start;
  }

  @media (max-width: 1100px) {
    .dashboard-columns {
      grid-template-columns: 1fr;
    }
  }

  .panel{
    border: 1px solid #e5e7eb;
    border-radius: var(--b2s-radius-lg);
    background: #fff;
    padding: 12px;
  }
  .panel__header{ margin-bottom: 10px; }
  h2{ margin: 0; font-size: var(--b2s-fs-lg); }
  .panel__hint{ color:var(--b2s-color-text-muted); font-size:var(--b2s-fs-md); margin-top: 4px; }
  .activity{ list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:10px; }
  .activity li{ border-top:1px dashed #e5e7eb; padding-top:10px; }
  .activity li:first-child{ border-top: none; padding-top:0; }
  .activity__main{ display:flex; gap:8px; flex-wrap:wrap; }
  .activity__action{ font-weight:700; }
  .activity__target{ color:var(--b2s-color-text-soft); }
  .activity__meta{ color:var(--b2s-color-text-muted); font-size:var(--b2s-fs-md); margin-top: 4px; display:flex; gap:6px; align-items:center; }
  .dot{ opacity:.7; }
</style>
