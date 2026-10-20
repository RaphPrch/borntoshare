<script lang="ts">
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import { formatDateTime } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import DashboardShell from './DashboardShell.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { formatActivityItem } from '$lib/activity/format';

  // Expected (safe) shape:
  // data.stats: { storage_roots, storage_endpoints, admins, pending_requests }
  // data.activities: [{ action, target_type, target_name, created_at, actor_display_name }]
  export let data: any;

  const stats = data?.stats ?? data?.summary ?? {};
  const activities = Array.isArray(data?.activities) ? data.activities : [];

  const kpi = [
    { key: 'storage_roots', label: t('Storage Roots'), href: '/storage-roots', icon: 'bi-folder2-open', tone: 'info' },
    { key: 'storage_endpoints', label: t('Storage Endpoints'), href: '/admin/storage-endpoints', icon: 'bi-hdd-network', tone: 'purple' },
    { key: 'admins', label: t('Admins'), href: '/admin/identity', icon: 'bi-person-gear', tone: 'success' },
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
</DashboardShell>

<style>
  @media (max-width: 1100px){
  }
  @media (max-width: 640px){
  }

  .panel{
    border: 1px solid #e5e7eb;
    border-radius: var(--b2s-radius-lg);
    background: #fff;
    padding: 12px;
  }
  .panel__header{ margin-bottom: 10px; }
  h2{ margin: 0; font-size: var(--b2s-fs-lg); }
  .panel__hint{ color:#64748b; font-size:var(--b2s-fs-md); margin-top: 4px; }
  .activity{ list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:10px; }
  .activity li{ border-top:1px dashed #e5e7eb; padding-top:10px; }
  .activity li:first-child{ border-top: none; padding-top:0; }
  .activity__main{ display:flex; gap:8px; flex-wrap:wrap; }
  .activity__action{ font-weight:700; }
  .activity__target{ color:#475569; }
  .activity__meta{ color:#64748b; font-size:var(--b2s-fs-md); margin-top: 4px; display:flex; gap:6px; align-items:center; }
  .dot{ opacity:.7; }
</style>
