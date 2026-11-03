<script lang="ts">
  import { t } from '$lib/i18n';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { formatDate, timeAgo } from '$lib/utils/format';
  import { getRequestStatusMeta, requestToneVariant } from '$lib/utils/access-request-status';
  import type { DashboardRequest, UserDashboardMePayload } from '$lib/api/dashboard';
  import DashboardShell from './DashboardShell.svelte';

  /** Dashboard of a user who is not an administrator; a guardian also sees the requests on their folders. */
  export let data: UserDashboardMePayload;

  $: guardian = data.role === 'guardian' ? data.guardian : undefined;
  $: mine = data.mine;

  const href = (row: DashboardRequest, status = 'all') => `/access-requests?status=${status}&request=${row.request_id}`;
  const access = (row: DashboardRequest) =>
    String(row.permission ?? '').toLowerCase().includes('write') ? t('Modify') : t('Read');
  const failed = (row: DashboardRequest) => ['FAILED', 'ERROR', 'TIMED_OUT'].includes(String(row.latest_execution_status ?? '').toUpperCase());
  const tone = (count: number, alarm: 'warning' | 'danger') => (count > 0 ? alarm : 'success');
</script>

<DashboardShell
  title={t('Dashboard')}
  subtitle={guardian ? t('Your requests and the folders you guard') : t('Your requests and your accesses')}
>
  <a slot="actions" class="b2s-btn b2s-btn-primary" href="/access-requests?create=1">
    <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Request access')}
  </a>

  {#if guardian}
    <section aria-labelledby="guardian-title">
      <h2 id="guardian-title">{t('Folders you guard')}</h2>
      <div class="b2s-kpi-grid">
        <KpiCard label={t('Requests to decide')} value={guardian.to_decide} icon="bi-inbox" tone={tone(guardian.to_decide, 'warning')} href="/access-requests?status=pending"
          hint={guardian.overdue ? t('{count} waiting for more than 3 days', { count: guardian.overdue }) : null} />
        <KpiCard label={t('In error')} value={guardian.failed} icon="bi-exclamation-octagon" tone={tone(guardian.failed, 'danger')} href="/access-requests?status=all"
          hint={t('Requests the file server or the directory refused')} />
        <KpiCard label={t('Folders to look at')} value={guardian.folders_with_alerts} icon="bi-folder-x" tone={tone(guardian.folders_with_alerts, 'warning')} href="/storage-roots?filter=review"
          hint={t('{count} folder(s) guarded', { count: guardian.folders })} />
        <KpiCard label={t('Ending within 30 days')} value={guardian.ending_30d} icon="bi-calendar-event" tone="info" href="/access-requests?status=applied"
          hint={t('{count} access(es) in force', { count: guardian.active })} />
      </div>
      <div class="b2s-kpi-grid">
        <KpiCard label={t('Accepted (30 days)')} value={guardian.approved_30d ?? 0} icon="bi-check-circle" tone="success" href="/access-requests?status=applied" />
        <KpiCard label={t('Refused (30 days)')} value={guardian.refused_30d ?? 0} icon="bi-x-circle" tone="neutral" href="/access-requests?status=closed" />
        <KpiCard label={t('Revoked (30 days)')} value={guardian.revoked_30d ?? 0} icon="bi-person-dash" tone="neutral" href="/access-requests?status=closed" />
        <KpiCard label={t('Accesses in force')} value={guardian.active} icon="bi-unlock" tone="info" href="/access-requests?status=applied"
          hint={t('{count} folder(s) guarded', { count: guardian.folders })} />
      </div>
    </section>
  {/if}

  <section aria-labelledby="mine-title">
    <h2 id="mine-title">{t('My requests')}</h2>
    <div class="b2s-kpi-grid">
      <KpiCard label={t('Pending')} value={mine.pending} icon="bi-hourglass-split" tone="info" href="/access-requests?status=pending" />
      <KpiCard label={t('Accesses in force')} value={mine.active} icon="bi-unlock" tone="success" href="/storage-roots"
        hint={mine.ending_30d ? t('{count} ending within 30 days', { count: mine.ending_30d }) : null} />
      <KpiCard label={t('In error')} value={mine.failed} icon="bi-exclamation-octagon" tone={tone(mine.failed, 'danger')} href="/access-requests?status=all" />
      <KpiCard label={t('Refused (30 days)')} value={mine.refused_30d} icon="bi-x-circle" tone="neutral" href="/access-requests?status=closed" />
    </div>
  </section>

  <div class="columns">
    <section class="panel">
      {#if guardian}
        <header><h2>{t('To decide')}</h2><a href="/access-requests?status=pending">{t('See all')}</a></header>
        {#each [...(data.guarded_failed ?? []), ...(data.to_decide ?? [])] as row (row.request_id)}
          <a class="row" href={href(row, failed(row) ? 'all' : 'pending')}>
            <span class="row__main"><strong>{row.storage_root_name ?? '—'}</strong><small>{t('For {name}', { name: row.requested_for_display ?? '—' })} · {access(row)}</small></span>
            {#if failed(row)}
              <StatusBadge variant="error" label={t('In error')} />
            {:else}
              <StatusBadge variant={row.overdue ? 'error' : 'warning'} label={row.overdue ? t('Overdue') : t('To decide')} />
            {/if}
            <small class="row__when">{timeAgo(row.created_at)}</small>
          </a>
        {:else}
          <EmptyStateInline message={t('Nothing to decide.')} />
        {/each}
      {:else}
        <header><h2>{t('My latest requests')}</h2><a href="/access-requests?status=all">{t('See all')}</a></header>
        {#each data.my_requests as row (row.request_id)}
          {@const meta = getRequestStatusMeta(row.status)}
          <a class="row" href={href(row)}>
            <span class="row__main"><strong>{row.storage_root_name ?? '—'}</strong><small>{row.request_code ?? ''} · {access(row)}</small></span>
            <StatusBadge variant={failed(row) ? 'error' : requestToneVariant(meta.tone)} label={failed(row) ? t('In error') : meta.label} />
            <small class="row__when">{timeAgo(row.created_at)}</small>
          </a>
        {:else}
          <EmptyStateInline message={t('No request yet.')} />
        {/each}
      {/if}
    </section>

    <section class="panel">
      <header><h2>{t('My accesses ending soon')}</h2><a href="/storage-roots">{t('My folders')}</a></header>
      {#each data.my_ending as row (row.request_id)}
        <a class="row" href={href(row, 'applied')}>
          <span class="row__main"><strong>{row.storage_root_name ?? '—'}</strong><small>{access(row)}</small></span>
          <small class="row__when">{t('Ends on {date}', { date: formatDate(row.expires_at) })}</small>
        </a>
      {:else}
        <EmptyStateInline message={t('No access ends within 30 days.')} />
      {/each}
    </section>
  </div>
</DashboardShell>

<style>
  h2 { margin: 8px 0 12px; font-size: var(--b2s-fs-lg); font-weight: 600; color: var(--b2s-color-text); }
  .columns { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 16px; align-items: start; }
  .panel { display: flex; flex-direction: column; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .panel header { display: flex; align-items: baseline; justify-content: space-between; }
  .panel header h2 { margin: 0 0 8px; }
  .panel header a { font-size: var(--b2s-text-sm); }
  .row { display: grid; grid-template-columns: minmax(0, 1fr) auto 84px; gap: 12px; align-items: center; padding: 9px 0; border-top: 1px solid var(--b2s-color-border); color: inherit; text-decoration: none; }
  .row:hover strong { text-decoration: underline; }
  .row__main { display: flex; flex-direction: column; min-width: 0; }
  .row__main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .row__main small, .row__when { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .row__when { text-align: right; }
</style>
