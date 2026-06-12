<script lang="ts">
  import { goto } from '$app/navigation';
  import DashboardShell from './DashboardShell.svelte';
  import EmptyStateInline from '$lib/components/common/EmptyStateInline.svelte';
  import { formatActivityItem } from '$lib/activity/format';

  // Expected (safe) shape:
  // data.stats: { storage_roots, storage_endpoints, admins, pending_requests }
  // data.activities: [{ action, target_type, target_name, created_at, actor_display_name }]
  export let data: any;

  const stats = data?.stats ?? data?.summary ?? {};
  const activities = Array.isArray(data?.activities) ? data.activities : [];

  const kpi = [
    { key: 'storage_roots', label: 'Storage Roots', href: '/storage-roots' },
    { key: 'storage_endpoints', label: 'Storage Endpoints', href: '/admin/storage-endpoints' },
    { key: 'admins', label: 'Admins', href: '/admin/identity' },
    { key: 'pending_requests', label: 'Pending Requests', href: '/access-requests' }
  ];

  const num = (v: any) => (Number.isFinite(Number(v)) ? Number(v) : 0);

  const timeLabel = (value: unknown): string => {
    const text = String(value ?? '').trim();
    if (!text) return '—';
    const d = new Date(text);
    if (Number.isNaN(d.getTime())) return text;
    return d.toLocaleString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };
</script>

<DashboardShell title="Admin Dashboard" subtitle="Platform Operations Overview">
  <div class="kpi-grid">
    {#each kpi as item}
      <button class="kpi" on:click={() => goto(item.href)}>
        <div class="kpi__label">{item.label}</div>
        <div class="kpi__value">{num(stats[item.key])}</div>
        <div class="kpi__hint">Open</div>
      </button>
    {/each}
  </div>

  <section class="panel">
    <div class="panel__header">
      <h2>Latest admin activity</h2>
      <div class="panel__hint">Recent actions across the platform</div>
    </div>

    {#if activities.length === 0}
      <EmptyStateInline message="No recent activity." />
    {:else}
      <ul class="activity">
        {#each activities.slice(0, 8) as a}
          {@const rendered = formatActivityItem(a)}
          <li>
            <div class="activity__main">
              <span class="activity__action">{rendered.title ?? 'Event'}</span>
              <span class="activity__target">
                {rendered.subtitle1 ?? ((a.target_type ?? 'target') + (a.target_name ? ` • ${a.target_name}` : ''))}
              </span>
            </div>
            <div class="activity__meta">
              <span>{a.actor_display_name ?? '—'}</span>
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
  .kpi-grid{
    display:grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  @media (max-width: 1100px){
    .kpi-grid{ grid-template-columns: repeat(2, minmax(0,1fr)); }
  }
  @media (max-width: 640px){
    .kpi-grid{ grid-template-columns: 1fr; }
  }
  .kpi{
    text-align:left;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 12px 12px 10px;
    background: #fff;
    cursor: pointer;
  }
  .kpi:hover{ border-color:#c7d2fe; box-shadow: 0 1px 10px rgba(15,23,42,.06); }
  .kpi__label{ color:#475569; font-weight:600; font-size:.9rem; }
  .kpi__value{ font-size: 1.55rem; font-weight:800; margin-top: 6px; }
  .kpi__hint{ margin-top: 8px; color:#64748b; font-size:.85rem; }

  .panel{
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    background: #fff;
    padding: 12px;
  }
  .panel__header{ margin-bottom: 10px; }
  h2{ margin: 0; font-size: 1.05rem; }
  .panel__hint{ color:#64748b; font-size:.9rem; margin-top: 4px; }
  .activity{ list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:10px; }
  .activity li{ border-top:1px dashed #e5e7eb; padding-top:10px; }
  .activity li:first-child{ border-top: none; padding-top:0; }
  .activity__main{ display:flex; gap:8px; flex-wrap:wrap; }
  .activity__action{ font-weight:700; }
  .activity__target{ color:#475569; }
  .activity__meta{ color:#64748b; font-size:.85rem; margin-top: 4px; display:flex; gap:6px; align-items:center; }
  .dot{ opacity:.7; }
</style>
