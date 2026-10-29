<script lang="ts">
  import { t, intlLocale } from '$lib/i18n';

  /** Access requests submitted per day; missing days are drawn as zero. */
  export let series: { day: string; submitted: number; applied: number }[] = [];
  export let days = 30;

  const pad = (n: number) => String(n).padStart(2, '0');
  const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  $: byDay = new Map(series.map((row) => [row.day, row]));
  $: points = Array.from({ length: days }, (_, index) => {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - (days - 1 - index));
    const key = isoDay(date);
    const row = byDay.get(key);
    return {
      key,
      label: date.toLocaleDateString(intlLocale(), { day: '2-digit', month: 'short' }),
      submitted: Number(row?.submitted ?? 0),
      applied: Number(row?.applied ?? 0)
    };
  });
  $: total = points.reduce((sum, p) => sum + p.submitted, 0);
  // Clean axis maximum: next "nice" number above the highest day
  $: maxValue = (() => {
    const peak = Math.max(1, ...points.map((p) => p.submitted));
    const step = peak <= 5 ? 1 : peak <= 10 ? 2 : peak <= 25 ? 5 : 10;
    return Math.ceil(peak / step) * step;
  })();
  $: ticks = [maxValue, maxValue / 2, 0].map((v) => Math.round(v));

  let hovered: number | null = null;
</script>

<figure class="req-chart">
  <figcaption class="req-chart__head">
    <span class="req-chart__title">{t('Access requests submitted')}</span>
    <span class="req-chart__meta">{t('{total} over the last {days} days', { total, days })}</span>
  </figcaption>

  <div class="req-chart__plot" role="img" aria-label={t('{total} access requests submitted over the last {days} days', { total, days })}>
    <div class="req-chart__axis" aria-hidden="true">
      {#each ticks as tick}<span>{tick}</span>{/each}
    </div>
    <div class="req-chart__area">
      <div class="req-chart__grid" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="req-chart__bars" style={`grid-template-columns: repeat(${days}, 1fr)`}>
        {#each points as point, index (point.key)}
          <div
            class="req-chart__slot"
            role="presentation"
            on:mouseenter={() => (hovered = index)}
            on:mouseleave={() => (hovered = null)}
          >
            <span class="req-chart__bar" style={`height:${(point.submitted / maxValue) * 100}%`}></span>
            {#if hovered === index}
              <div class="req-chart__tip" class:is-right={index > days * 0.7}>
                <strong>{point.label}</strong>
                <span>{t('{count} submitted', { count: point.submitted })}</span>
                <span>{t('{count} applied', { count: point.applied })}</span>
              </div>
            {/if}
          </div>
        {/each}
      </div>
      <div class="req-chart__labels" aria-hidden="true" style={`grid-template-columns: repeat(${days}, 1fr)`}>
        {#each points as point, index (point.key)}
          <span>{(days - 1 - index) % 7 === 0 ? point.label : ''}</span>
        {/each}
      </div>
    </div>
  </div>

  <table class="visually-hidden">
    <caption>{t('Access requests submitted')}</caption>
    <thead><tr><th>{t('Day')}</th><th>{t('Submitted')}</th><th>{t('Applied')}</th></tr></thead>
    <tbody>
      {#each points as point (point.key)}
        <tr><td>{point.label}</td><td>{point.submitted}</td><td>{point.applied}</td></tr>
      {/each}
    </tbody>
  </table>
</figure>

<style>
  .req-chart {
    margin: 0;
    padding: 16px 20px 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .req-chart__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }

  .req-chart__title {
    font-size: var(--b2s-fs-lg);
    font-weight: 600;
    color: var(--b2s-color-text);
  }

  .req-chart__meta {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .req-chart__plot {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
  }

  .req-chart__axis {
    height: 160px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: flex-end;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-variant-numeric: tabular-nums;
    transform: translateY(-0.5em);
  }

  .req-chart__area {
    position: relative;
    min-width: 0;
  }

  .req-chart__grid {
    position: absolute;
    inset: 0 0 auto 0;
    height: 160px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    pointer-events: none;
  }

  .req-chart__grid span {
    border-top: 1px solid #eef2f7;
  }

  .req-chart__grid span:last-child {
    border-top-color: var(--b2s-color-border-mid);
  }

  .req-chart__bars {
    position: relative;
    height: 160px;
    display: grid;
    align-items: end;
  }

  .req-chart__slot {
    position: relative;
    height: 100%;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding: 0 1px;
  }

  .req-chart__slot:hover {
    background: rgba(59, 111, 216, 0.06);
  }

  .req-chart__bar {
    width: 100%;
    max-width: 20px;
    border-radius: 4px 4px 0 0;
    background: #3b6fd8;
  }

  .req-chart__tip {
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    z-index: 2;
    transform: translateX(-50%);
    display: grid;
    gap: 2px;
    padding: 8px 10px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    box-shadow: 0 6px 18px rgba(18, 31, 64, 0.12);
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
    pointer-events: none;
  }

  .req-chart__tip.is-right {
    left: auto;
    right: 0;
    transform: none;
  }

  .req-chart__tip strong {
    color: var(--b2s-color-text);
  }

  .req-chart__labels {
    display: grid;
    margin-top: 6px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
  }
</style>
