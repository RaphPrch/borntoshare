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

  const FIRST = 4;
  let isAdmin = $derived(($page.data as any)?.navigation?.canSeeAdmin === true);
  let roots = $state<Record<string, any>[] | null>(null);
  let exposure = $state<ExposureSummary | null>(null);
  let topology = $state<TopologySummary | null>(null);
  let fivesScore = $state<number | null>(null);

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
  let insights = $derived(roots ? buildInsights(roots, $governanceEnabled) : []);
  let first = $derived(insights.filter((insight) => insight.tone === 'bad' || insight.tone === 'warn').slice(0, FIRST));
  let volume = $derived((roots ?? []).reduce((sum, row) => sum + num(row.content_size_bytes ?? row.estimated_size_bytes), 0));
  let alerted = $derived(roots ? foldersMatching(roots, 'est:alerte') : []);
  let alerts = $derived(alerted.reduce((sum, row) => sum + num(row.open_alerts_count), 0));
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
</style>
