<script lang="ts">
  import { governanceEnabled } from '$lib/utils/features';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { t } from '$lib/i18n';
  import { formatDate } from '$lib/utils/format';
  import { getRequestStatusMeta, requestToneVariant } from '$lib/utils/access-request-status';
  import type { DashboardRequest, UserDashboardMePayload } from '$lib/api/dashboard';

  interface Props {
    /** Dashboard of a user who is not an administrator; a guardian also sees the requests on their folders. */
    data: UserDashboardMePayload;
  }

  let { data }: Props = $props();

  let guardian = $derived(data.role === 'guardian' ? data.guardian : undefined);
  let mine = $derived(data.mine);

  const todayText = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  const today = todayText.charAt(0).toUpperCase() + todayText.slice(1);
  const href = (row: DashboardRequest, status = 'all') => `/access-requests?status=${status}&request=${row.request_id}`;
  const access = (row: DashboardRequest) =>
    String(row.permission ?? '').toLowerCase().includes('write') ? t('Modify') : t('Read');
  const failed = (row: DashboardRequest) => ['FAILED', 'ERROR', 'TIMED_OUT'].includes(String(row.latest_execution_status ?? '').toUpperCase());
  const TONE: Record<string, string> = { success: 'ok', warning: 'warn', error: 'bad', info: 'info', muted: 'mut' };
  // The sentence of the day: what needs this person first
  let headline = $derived(
    guardian && guardian.to_decide ? t('{count} request(s) wait for your decision', { count: guardian.to_decide })
      : mine.failed ? t('{count} of your requests could not be applied', { count: mine.failed })
        : mine.pending ? t('{count} of your requests are on their way', { count: mine.pending })
          : t('Nothing waits for you today')
  );
</script>

<section class="v2 ud">
  {#if !$governanceEnabled}
    <!-- A 5S-only installation: no request; the 5S of the folders is for their guardians and the administrators -->
    <div class="v2-head"><div><small class="ud__kick">{today}</small><h1>{t('Dashboard')}</h1>
      <p>{t('Nothing to do here: the 5S of the folders is followed by their guardians and the administrators.')}</p></div></div>
  {:else}
    <div class="v2-head">
      <div>
        <small class="ud__kick">{today}</small>
        <h1>{headline}</h1>
        <p>{guardian ? t('Your requests and the folders you guard') : t('Your requests and your accesses')}</p>
      </div>
      <div class="v2-head__act"><a class="b2s-btn b2s-btn-primary" href="/access-requests/new"><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Request access')}</a></div>
    </div>

    {#if guardian}
      <div class="v2-sh"><h2>{t('Folders you guard')}</h2></div>
      <div class="v2-stats">
        <a class="v2-stat" href="/access-requests?status=pending"><small>{t('Requests to decide')}</small><b class:ud__warn={guardian.to_decide > 0}>{guardian.to_decide}</b>
          <span>{guardian.overdue ? t('{count} waiting for more than 3 days', { count: guardian.overdue }) : t('none overdue')}</span></a>
        <a class="v2-stat" href="/access-requests?status=all"><small>{t('In error')}</small><b class:ud__bad={guardian.failed > 0}>{guardian.failed}</b><span>{t('Requests the file server or the directory refused')}</span></a>
        <a class="v2-stat" href="/storage-roots?filter=review"><small>{t('Folders to look at')}</small><b class:ud__warn={guardian.folders_with_alerts > 0}>{guardian.folders_with_alerts}</b>
          <span>{t('{count} folder(s) guarded', { count: guardian.folders })}</span></a>
        <a class="v2-stat" href="/access-requests?status=applied"><small>{t('Accesses in force')}</small><b>{guardian.active}</b>
          <span>{t('{count} ending within 30 days', { count: guardian.ending_30d })}</span></a>
        <a class="v2-stat" href="/access-requests?status=closed"><small>{t('Last 30 days')}</small><b>{guardian.approved_30d ?? 0}</b>
          <span>{t('accepted · {refused} refused · {revoked} revoked', { refused: guardian.refused_30d ?? 0, revoked: guardian.revoked_30d ?? 0 })}</span></a>
      </div>
    {/if}

    <div class="v2-sh"><h2>{t('My requests')}</h2></div>
    <div class="v2-stats">
      <a class="v2-stat" href="/access-requests?status=pending"><small>{t('Pending')}</small><b>{mine.pending}</b><span>{t('on their way')}</span></a>
      <a class="v2-stat" href="/storage-roots"><small>{t('Accesses in force')}</small><b>{mine.active}</b>
        <span>{mine.ending_30d ? t('{count} ending within 30 days', { count: mine.ending_30d }) : t('none ends within 30 days')}</span></a>
      <a class="v2-stat" href="/access-requests?status=all"><small>{t('In error')}</small><b class:ud__bad={mine.failed > 0}>{mine.failed}</b><span>{t('to look at')}</span></a>
      <a class="v2-stat" href="/access-requests?status=closed"><small>{t('Refused (30 days)')}</small><b>{mine.refused_30d}</b><span>{t('last 30 days')}</span></a>
    </div>

    <div class="v2-cols2">
      <div class="v2-sec">
        {#if guardian}
          <div class="v2-sh"><h2>{t('To decide')}</h2><div class="v2-sh__r"><a href="/access-requests?status=pending">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each [...(data.guarded_failed ?? []), ...(data.to_decide ?? [])] as row (row.request_id)}
              <li><a class="v2-fi" href={href(row, failed(row) ? 'all' : 'pending')}>
                <div class="v2-fi__t"><b>{row.storage_root_name ?? '—'}</b><small>{t('For {name}', { name: row.requested_for_display ?? '—' })} · {access(row)}</small></div>
                <span class="v2-fi__r"><span class={`v2-tag is-${failed(row) || row.overdue ? 'bad' : 'warn'}`}>{failed(row) ? t('In error') : row.overdue ? t('Overdue') : t('To decide')}</span>
                  <small><RelativeTime value={row.created_at} /></small></span>
              </a></li>
            {:else}
              <li class="v2-empty">{t('Nothing to decide.')}</li>
            {/each}
          </ul>
        {:else}
          <div class="v2-sh"><h2>{t('My latest requests')}</h2><div class="v2-sh__r"><a href="/access-requests?status=all">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each data.my_requests as row (row.request_id)}
              {@const meta = getRequestStatusMeta(row.status)}
              <li><a class="v2-fi" href={href(row)}>
                <div class="v2-fi__t"><b>{row.storage_root_name ?? '—'}</b><small>{row.request_code ?? ''} · {access(row)}</small></div>
                <span class="v2-fi__r"><span class={`v2-tag is-${failed(row) ? 'bad' : TONE[requestToneVariant(meta.tone)] ?? 'mut'}`}>{failed(row) ? t('In error') : meta.label}</span>
                  <small><RelativeTime value={row.created_at} /></small></span>
              </a></li>
            {:else}
              <li class="v2-empty">{t('No request yet.')} <a href="/access-requests/new">{t('New access request')}</a></li>
            {/each}
          </ul>
        {/if}
      </div>
      <div class="v2-sec">
        <div class="v2-sh"><h2>{t('My accesses ending soon')}</h2><div class="v2-sh__r"><a href="/storage-roots">{t('My folders')}</a></div></div>
        <ul class="v2-feed">
          {#each data.my_ending as row (row.request_id)}
            <li><a class="v2-fi" href={href(row, 'applied')}>
              <div class="v2-fi__t"><b>{row.storage_root_name ?? '—'}</b><small>{access(row)}</small></div>
              <span class="v2-fi__r"><small>{t('Ends on {date}', { date: formatDate(row.expires_at) })}</small></span>
            </a></li>
          {:else}
            <li class="v2-empty">{t('No access ends within 30 days.')}</li>
          {/each}
        </ul>
      </div>
    </div>
  {/if}
</section>

<style>
  .ud { display: grid; gap: 18px; padding: var(--b2s-page-padding); }
  .ud__kick { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); font-weight: 600; }
  .ud h2 { margin: 0; font-size: 17px; font-weight: 600; }
  .ud__warn { color: #b45309; }
  .ud__bad { color: #b42318; }
</style>
