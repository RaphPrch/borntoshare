<script lang="ts">
  /**
   * Insights & Recommendations › Overview: the state of the data in one place. Key figures, coverage (measured, with
   * a guardian, governed, servers available), and the recommendations to handle first. Every figure opens the list
   * behind it; the details live in the other tabs (Recommendations, Topology, Exposure, Reports).
   */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { apiGetData, apiGetList } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RingStat from '$lib/components/ui/RingStat.svelte';
  import InsightCards from '$lib/components/insights/InsightCards.svelte';
  import { t } from '$lib/i18n';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { formatBytes } from '$lib/utils/format';
  import { foldersMatching } from '$lib/components/storage-roots/folder-query';
  import { INSIGHT_FIELDS, buildInsights } from '$lib/utils/insights';
  import { coverageRings, type ExposureSummary, type TopologySummary } from '$lib/utils/coverage';
  import { coverageTone } from '$lib/utils/ring';
  import Sparkline from '$lib/components/ui/Sparkline.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { formatDate } from '$lib/utils/format';
  import { buildTrends, trendVerdict, type HistoryPoint, type Trend } from '$lib/utils/trends';

  const FIRST = 4;
  let isAdmin = $derived(($page.data as any)?.navigation?.canSeeAdmin === true);
  let roots = $state<Record<string, any>[] | null>(null);
  let exposure = $state<ExposureSummary | null>(null);
  let topology = $state<TopologySummary | null>(null);
  let fivesScore = $state<number | null>(null);
  // Trends (administrators: the figures of every folder): one snapshot a day, taken by core-service
  let period = $state('90');
  let history = $state<HistoryPoint[] | null>(null);
  $effect(() => {
    if (!isAdmin) return;
    const days = period;
    history = null;
    apiGetData<HistoryPoint[]>(fetch, '/insights/history', { days }).then((data) => (history = data ?? [])).catch(() => (history = []));
  });

  onMount(() => {
    // Each source on its own: the page shows what has come, the others fill in (never a « 0 » for « not read yet »)
    void apiGetList<Record<string, any>>(fetch, '/storage-roots/context', { fields: `${INSIGHT_FIELDS},open_alerts_count` })
      .then((rows) => (roots = rows)).catch(() => (roots = []));
    if ($governanceEnabled) void apiGetData<{ summary: ExposureSummary }>(fetch, '/storage-roots/exposure').then((data) => (exposure = data?.summary ?? null)).catch(() => null);
    if (isAdmin) void apiGetData<{ summary: TopologySummary }>(fetch, '/storage-topology').then((data) => (topology = data?.summary ?? null)).catch(() => null);
    if ($fivesEnabled) void apiGetData<{ score: number | null }>(fetch, '/modules/fives/five-s').then((data) => (fivesScore = data?.score ?? null)).catch(() => null);
  });

  const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
  let rings = $derived(coverageRings({ roots, governance: $governanceEnabled, exposure, topology: isAdmin ? topology : undefined }));
  let insights = $derived(roots ? buildInsights(roots, { governance: $governanceEnabled, fives: $fivesEnabled }) : []);
  let first = $derived(insights.filter((insight) => insight.tone === 'bad' || insight.tone === 'warn').slice(0, FIRST));
  let volume = $derived((roots ?? []).reduce((sum, row) => sum + num(row.content_size_bytes ?? row.estimated_size_bytes), 0));
  let alerted = $derived(roots ? foldersMatching(roots, 'est:alerte') : []);
  let alerts = $derived(alerted.reduce((sum, row) => sum + num(row.open_alerts_count), 0));
  let trends = $derived(history ? buildTrends(history) : []);
  const show = (trend: Trend, value: number | null) =>
    value == null ? '—' : trend.kind === 'percent' ? `${Math.round(value)} %` : trend.kind === 'bytes' ? formatBytes(value) : Math.round(value).toLocaleString('fr-FR');
  const showDelta = (trend: Trend) => {
    if (trend.delta == null) return '';
    const sign = trend.delta > 0 ? '+' : trend.delta < 0 ? '−' : '±';
    const size = Math.abs(trend.delta);
    return `${sign}${trend.kind === 'percent' ? `${size.toFixed(1)} pt` : trend.kind === 'bytes' ? formatBytes(size) : Math.round(size).toLocaleString('fr-FR')}`;
  };
</script>

<svelte:head><title>Insights & Recommendations · BornToShare</title></svelte:head>

<section class="v2 io">
  <div class="v2-head">
    <div>
      <h1>Insights &amp; Recommendations</h1>
      <p>{t('The state of the data of the folders you may see: what is covered, what is exposed, what to handle first.')}</p>
    </div>
  </div>

  <div class="v2-stats">
    <a class="v2-stat" href="/storage-roots"><i class="bi bi-folder2-open" aria-hidden="true"></i><small>{t('Governed folders')}</small><b>{roots ? roots.length : '…'}</b><span>{t('in your scope')}</span></a>
    <a class="v2-stat" href="/storage-roots"><i class="bi bi-database" aria-hidden="true"></i><small>{t('Measured volume')}</small><b>{roots ? formatBytes(volume) : '…'}</b><span>{t('last measures')}</span></a>
    <a class="v2-stat" href={`/storage-roots?q=${encodeURIComponent('est:alerte')}`}><i class={`bi bi-bell ${alerts ? 'is-warn' : ''}`} aria-hidden="true"></i><small>{t('Open alerts')}</small><b>{roots ? alerts : '…'}</b><span>{t('in {count} folder(s)', { count: alerted.length })}</span></a>
    <a class="v2-stat" href="/insights/recommendations"><i class="bi bi-lightbulb" aria-hidden="true"></i><small>{t('Recommendations')}</small><b>{roots ? insights.length : '…'}</b><span>{t('{count} to handle first', { count: first.length })}</span></a>
    {#if $fivesEnabled}
      <a class="v2-stat" href="/five-s"><i class="bi bi-stars" aria-hidden="true"></i><small>{t('Average 5S score')}</small><b>{fivesScore ?? '—'}</b><span>{t('on the measured folders')}</span></a>
    {/if}
  </div>

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Coverage')}</h2></div>
    <div class="io__rings">
      {#each rings as ring (ring.key)}
        <a class="io__ring" href={ring.href}>
          <RingStat value={ring.value} size={76} tone={coverageTone(ring.value)} label={`${ring.label}: ${ring.value == null ? '—' : Math.round(ring.value) + ' %'}`} />
          <span><b>{ring.label}</b><small>{ring.detail}</small></span>
        </a>
      {/each}
    </div>
  </div>

  {#if isAdmin}
    <div class="v2-sec">
      <div class="v2-sh"><h2>{t('Trends')}</h2>
        <div class="v2-sh__r"><SegmentedFilter options={[{ key: '30', label: t('30 days') }, { key: '90', label: t('90 days') }, { key: '365', label: t('1 year') }]} bind:value={period} ariaLabel={t('Period')} /></div></div>
      {#if !history}
        <LoadingState block skeleton="rows" rows={2} />
      {:else if history.length < 2}
        <p class="v2-hint">{history.length
          ? t('The history started on {date}: the curves appear from the second day (one snapshot a day, taken by the health check).', { date: formatDate(history[0].day) })
          : t('No snapshot yet: the first one is taken by the next health check, then one a day.')}</p>
      {/if}
      {#if history?.length}
        <div class="io__trends">
          {#each trends as trend (trend.key)}
            {@const verdict = trendVerdict(trend)}
            <a class="io__trend" href={trend.href}>
              <span class="io__trend-h"><small>{t(trend.label)}</small>
                {#if verdict}<span class={`v2-tag is-${verdict === 'better' ? 'ok' : verdict === 'worse' ? 'warn' : 'mut'}`}>{showDelta(trend)}</span>{/if}</span>
              <b>{show(trend, trend.last)}</b>
              <Sparkline points={trend.points} width={150} height={30} goodWhen={trend.goodWhen}
                title={t('{label}: {from} → {to}', { label: t(trend.label), from: show(trend, trend.points[0] ?? null), to: show(trend, trend.last) })} />
            </a>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('To handle first')}</h2>
      <div class="v2-sh__r"><a href="/insights/recommendations">{t('All recommendations')}</a></div></div>
    {#if !roots}
      <LoadingState block skeleton="rows" rows={2} />
    {:else if first.length}
      <InsightCards insights={first} total={roots.length} {isAdmin} />
    {:else}
      <p class="v2-empty">{t('Nothing urgent: the folders are well kept, or not measured yet.')}</p>
    {/if}
  </div>
</section>

<style>
  .io__rings { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
  .io__ring { display: flex; align-items: center; gap: 12px; padding: 4px; border-radius: var(--b2s-radius-md); color: inherit; text-decoration: none; }
  .io__ring:hover, .io__ring:focus-visible { background: var(--b2s-color-surface-hover); }
  .io__ring b { display: block; font-size: 14px; }
  .io__ring small { color: var(--b2s-color-text-muted); font-size: 12px; }
  .io__trends { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
  .io__trend { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border: 1px solid var(--b2s-color-border-soft); border-radius: var(--b2s-radius-md);
    color: inherit; text-decoration: none; }
  .io__trend:hover, .io__trend:focus-visible { border-color: var(--b2s-accent-border); }
  .io__trend-h { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
  .io__trend small { color: var(--b2s-color-text-muted); font-size: 12px; }
  .io__trend b { font-size: 20px; font-variant-numeric: tabular-nums; }
</style>
