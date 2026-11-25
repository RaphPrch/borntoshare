<script lang="ts">
  /**
   * My Tasks: what waits for the person signed in, gathered from the sources that already exist (nothing is computed
   * here that another page does not show): the requests to decide and the reviews (Access Management), the open
   * alerts of their folders (Governance Jobs), the recommendations (Insights & Recommendations, same rules), and their
   * own requests to follow (Dashboard). Each block leads to the page where it is handled.
   */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { apiGetData, apiGetList } from '$lib/api/client';
  // Types only: $lib/api/dashboard also serves the server (its functions cannot run in the browser)
  import type { DashboardRequest, UserDashboardMePayload } from '$lib/api/dashboard';
  import { listGovernanceAlerts, type GovernanceAlert } from '$lib/api/governance-alerts';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { accessRequestId, accessRequestRequesterName, accessRequestTargetLabel } from '$lib/mappers/access-requests.mapper';
  import { governanceEnabled } from '$lib/utils/features';
  import { formatDate } from '$lib/utils/format';
  import { INSIGHT_FIELDS, INSIGHT_ICONS, buildInsights, type Insight } from '$lib/utils/insights';

  type Review = { id: number; name: string; status: 'open' | 'closed'; due_at: string | null; total: number; decided: number };
  const SHOWN = 6;
  // The lists stop at these sizes (the route's limit, and ours for the alerts): beyond, the count says « + »
  const REQUESTS_LIMIT = 200;
  const ALERTS_LIMIT = 50;
  const countOf = (length: number, limit: number) => (length >= limit ? `${limit}+` : String(length));

  let nav = $derived(($page.data as any)?.navigation ?? {});
  let staff = $derived(Boolean(nav.canSeeStorageRoots));

  let loading = $state(true);
  let insightsLoading = $state(true);
  let toDecide = $state<any[]>([]);
  let reviews = $state<Review[]>([]);
  let alerts = $state<GovernanceAlert[]>([]);
  let insights = $state<Insight[]>([]);
  let me = $state<UserDashboardMePayload | null>(null);

  onMount(async () => {
    // Each source on its own: one that does not answer leaves its block empty, never the page
    const soft = <T,>(promise: Promise<T>, empty: T) => promise.catch(() => empty);
    const governance = $governanceEnabled;
    // The recommendations read every folder: they come after, the other blocks do not wait for them
    if (staff) {
      void soft(apiGetList<Record<string, any>>(fetch, '/storage-roots/context', { fields: INSIGHT_FIELDS }), []).then((roots) => {
        insights = buildInsights(roots, governance).filter((insight) => insight.tone !== 'mut');
        insightsLoading = false;
      });
    } else {
      insightsLoading = false;
    }
    const [pending, campaigns, open, mine] = await Promise.all([
      staff && governance ? soft(apiGetList<any>(fetch, '/access-requests', { status: 'pending' }), []) : Promise.resolve([]),
      staff && governance ? soft(apiGetData<Review[]>(fetch, '/access-reviews'), []) : Promise.resolve([] as Review[]),
      staff ? soft(listGovernanceAlerts(fetch, { status: 'open', limit: ALERTS_LIMIT }), []) : Promise.resolve([] as GovernanceAlert[]),
      soft(apiGetData<UserDashboardMePayload>(fetch, '/dashboard/me'), null)
    ]);
    toDecide = pending;
    reviews = (campaigns ?? []).filter((review) => review.status === 'open' && review.total > review.decided);
    alerts = open;
    me = mine;
    loading = false;
  });

  // Their own requests to follow: failed, or ending within 30 days (the Dashboard says the same)
  let followUp = $derived<DashboardRequest[]>([
    ...(me?.my_requests ?? []).filter((row) => String(row.latest_execution_status ?? '').toLowerCase() === 'failed'),
    ...(me?.my_ending ?? [])
  ]);
  const SEVERITY_TONE: Record<string, string> = { critical: 'bad', high: 'bad', warning: 'warn' };
  const severityLabel = (severity: unknown) =>
    ({ critical: t('Critical'), high: t('High'), warning: t('Warning'), info: t('Info') })[String(severity)] ?? String(severity ?? '');
  let total = $derived(toDecide.length + reviews.length + alerts.length + insights.length + followUp.length);
</script>

<svelte:head><title>My Tasks · BornToShare</title></svelte:head>

<section class="v2 tk">
  <div class="v2-head">
    <div>
      <h1>My Tasks</h1>
      <p>{t('What waits for you: requests to decide, reviews, alerts, recommendations and your own requests to follow.')}</p>
    </div>
  </div>

  {#if loading}
    <LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
  {:else if total === 0 && !insightsLoading}
    <div class="v2-sec"><p class="v2-empty">{t('Nothing waits for you.')}</p></div>
  {:else}
    <div class="v2-cols2">
      {#if toDecide.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('Requests to decide')}</h2><span class="v2-tag is-warn">{countOf(toDecide.length, REQUESTS_LIMIT)}</span>
            <div class="v2-sh__r"><a href="/access-requests?status=pending">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each toDecide.slice(0, SHOWN) as row (accessRequestId(row))}
              <li><a class="v2-fi" href={`/access-requests?status=pending&request=${accessRequestId(row)}`}>
                <div class="v2-fi__t"><b>{accessRequestTargetLabel(row)}</b><small>{t('For {name}', { name: accessRequestRequesterName(row) })}</small></div>
                <span class="v2-fi__r">{#if row.overdue}<span class="v2-tag is-bad">{t('Overdue')}</span>{/if}<small><RelativeTime value={row.created_at} /></small></span>
              </a></li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if reviews.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('Reviews to do')}</h2><span class="v2-tag is-warn">{reviews.length}</span>
            <div class="v2-sh__r"><a href="/access-reviews">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each reviews.slice(0, SHOWN) as review (review.id)}
              <li><a class="v2-fi" href={`/access-reviews/${review.id}`}>
                <div class="v2-fi__t"><b>{review.name}</b><small>{t('{left} decision(s) left out of {total}', { left: review.total - review.decided, total: review.total })}</small></div>
                <span class="v2-fi__r">{#if review.due_at}<small>{t('due {date}', { date: formatDate(review.due_at) })}</small>{/if}</span>
              </a></li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if alerts.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('Open alerts')}</h2><span class="v2-tag is-bad">{countOf(alerts.length, ALERTS_LIMIT)}</span>
            <div class="v2-sh__r"><a href={nav.canSeeObservability ? '/observability?tab=alerts' : '/storage-roots?q=est:alerte'}>{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each alerts.slice(0, SHOWN) as alert (alert.id ?? alert.alert_key)}
              <li><a class="v2-fi" href={alert.storage_root_id ? `/storage-roots?selected=${alert.storage_root_id}` : nav.canSeeObservability ? '/observability?tab=alerts' : '/storage-roots?q=est:alerte'}>
                <div class="v2-fi__t"><b>{alert.title ?? alert.alert_type}</b>{#if alert.message}<small>{alert.message}</small>{/if}</div>
                <span class="v2-fi__r"><span class={`v2-tag is-${SEVERITY_TONE[String(alert.severity)] ?? 'mut'}`}>{severityLabel(alert.severity)}</span>
                  {#if alert.last_seen_at}<small><RelativeTime value={alert.last_seen_at} /></small>{/if}</span>
              </a></li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if insightsLoading}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('Recommendations')}</h2></div>
          <LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
        </div>
      {:else if insights.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('Recommendations')}</h2><span class="v2-tag is-mut">{insights.length}</span>
            <div class="v2-sh__r"><a href="/reports">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each insights as insight (insight.key)}
              <li><a class="v2-fi" href={`/storage-roots?q=${encodeURIComponent(insight.query)}`}>
                <div class="v2-fi__t"><b><i class={`bi ${INSIGHT_ICONS[insight.key] ?? 'bi-lightbulb'}`} aria-hidden="true"></i> {insight.title}</b><small>{insight.detail}</small></div>
                <span class="v2-fi__r"><span class={`v2-tag is-${insight.tone}`}>{insight.big}</span></span>
              </a></li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if followUp.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('My requests to follow')}</h2><span class="v2-tag is-warn">{followUp.length}</span>
            <div class="v2-sh__r"><a href="/access-requests?status=all">{t('See all')}</a></div></div>
          <ul class="v2-feed">
            {#each followUp.slice(0, SHOWN) as row (`${row.request_id}-${row.expires_at}`)}
              <li><a class="v2-fi" href={`/access-requests?status=all&request=${row.request_id}`}>
                <div class="v2-fi__t"><b>{row.storage_root_name ?? '—'}</b>
                  <small>{String(row.latest_execution_status ?? '').toLowerCase() === 'failed' ? t('Not applied: to look at') : t('Ends {when}', { when: row.expires_at ? formatDate(row.expires_at) : '—' })}</small></div>
                <span class="v2-fi__r"><small><RelativeTime value={row.updated_at ?? row.created_at} /></small></span>
              </a></li>
            {/each}
          </ul>
        </div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .tk .v2-fi__t b i { margin-right: 4px; color: var(--b2s-accent-vivid); }
</style>
