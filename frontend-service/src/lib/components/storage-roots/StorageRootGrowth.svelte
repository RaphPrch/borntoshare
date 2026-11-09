<script lang="ts">
  import { apiGetData } from '$lib/api/client';
  import { t } from '$lib/i18n';
  import { formatBytes, formatDate } from '$lib/utils/format';

  /**
   * How the folder grows: one line of its size over the last 180 days (one point per measure), its pace and, when
   * it has a quota, the date the quota will be full at this pace. The trend needs a week of measures.
   */
  export let rootId: number | null = null;
  /** Changes after a new measure: the curve is read again */
  export let refreshKey: unknown = null;

  type Point = { at: string; bytes: number };
  type History = { points: Point[]; bytes_per_day: number | null; days_until_full: number | null; full_at: string | null; trend_after_days: number };
  let data: History | null = null;
  let loadedFor = '';
  let hovered: number | null = null;

  $: key = `${rootId}:${String(refreshKey)}`;
  $: if (rootId && key !== loadedFor) load();
  async function load() {
    loadedFor = key;
    data = await apiGetData<History>(fetch, `/modules/fives/storage-roots/${rootId}/growth`).catch(() => null);
  }

  const W = 320;
  const H = 64;
  $: points = data?.points ?? [];
  $: times = points.map((p) => Date.parse(p.at));
  $: minT = Math.min(...times);
  $: maxT = Math.max(...times);
  $: maxB = Math.max(1, ...points.map((p) => p.bytes));
  $: xy = points.map((p, i) => [maxT > minT ? ((times[i] - minT) / (maxT - minT)) * W : W, H - 4 - (p.bytes / maxB) * (H - 12)] as const);
  $: line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  $: area = xy.length > 1 ? `${line} L${W},${H} L0,${H} Z` : '';
  const pace = (value: number) => `${value >= 0 ? '+' : '−'}${formatBytes(Math.abs(value))}`;
</script>

{#if data}
  <div class="gr">
    <div class="gr__head">
      <h3>{t('Growth')}</h3>
      {#if data.bytes_per_day != null}
        <span class="gr__pace">{t('{pace} per day', { pace: pace(data.bytes_per_day) })}</span>
      {/if}
    </div>
    {#if points.length > 1}
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={t('Size of the folder over time')}
        on:mouseleave={() => (hovered = null)}>
        <path class="gr__area" d={area} />
        <path class="gr__line" d={line} />
        {#each xy as [x, y], index (index)}
          <rect x={x - 6} y="0" width="12" height={H} fill="transparent" role="presentation" on:mouseenter={() => (hovered = index)} />
          {#if hovered === index}<circle cx={x} cy={y} r="4" class="gr__dot" />{/if}
        {/each}
      </svg>
      <small class="gr__tip">{#if hovered != null}{formatDate(points[hovered].at)} · <b>{formatBytes(points[hovered].bytes)}</b>{:else}{t('{count} measure(s) since {date}', { count: points.length, date: formatDate(points[0].at) })}{/if}</small>
    {:else}
      <small class="gr__muted">{t('The curve appears with the next measures of the folder.')}</small>
    {/if}
    {#if data.days_until_full != null}
      <p class="gr__forecast" class:is-soon={data.days_until_full <= 30}>
        <i class="bi bi-hourglass-split" aria-hidden="true"></i>
        {data.days_until_full === 0 ? t('The quota is already full.') : t('At this pace the quota is full in about {days} days ({date}).', { days: data.days_until_full, date: formatDate(data.full_at) })}
      </p>
    {:else if data.bytes_per_day == null}
      <small class="gr__muted">{t('The trend and the date the quota will be full appear after {days} days of measures.', { days: data.trend_after_days })}</small>
    {/if}
  </div>
{/if}

<style>
  .gr { display: flex; flex-direction: column; gap: 6px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
  .gr__head { display: flex; align-items: baseline; justify-content: space-between; }
  .gr h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .gr__pace { font-size: var(--b2s-fs-xs); font-variant-numeric: tabular-nums; }
  svg { width: 100%; height: 64px; overflow: visible; }
  .gr__area { fill: var(--b2s-color-info-soft); }
  .gr__line { fill: none; stroke: var(--b2s-color-info-strong); stroke-width: 2; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
  .gr__dot { fill: var(--b2s-color-info-strong); stroke: var(--b2s-color-surface); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .gr__tip, .gr__muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .gr__tip b { color: var(--b2s-color-text); }
  .gr__forecast { display: flex; gap: 8px; align-items: center; margin: 2px 0 0; font-size: var(--b2s-fs-sm); }
  .gr__forecast.is-soon { color: var(--b2s-color-warning-strong, #9a5b00); font-weight: 600; }
</style>
