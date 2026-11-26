<script lang="ts">
  /**
   * A small trend line (the last measures of a folder): no axis, the last point marked, the growth said in its title.
   * Nothing is drawn with less than two points.
   */
  interface Props {
    points: number[];
    width?: number;
    height?: number;
    title?: string;
    /** The direction that is good news: « down » for a size (a growth is drawn as a warning), « up » for a coverage */
    goodWhen?: 'up' | 'down';
  }

  let { points, width = 64, height = 18, title = '', goodWhen = 'down' }: Props = $props();
  let shape = $derived.by(() => {
    if (points.length < 2) return null;
    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min || 1;
    const step = (width - 4) / (points.length - 1);
    const xy = points.map((value, index) => [2 + index * step, height - 2 - ((value - min) / span) * (height - 4)] as const);
    return { line: xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' '), last: xy[xy.length - 1], bad: goodWhen === 'down' ? points[points.length - 1] > points[0] : points[points.length - 1] < points[0] };
  });
</script>

{#if shape}
  <svg class="spark" class:is-up={shape.bad} viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={title}>
    {#if title}<title>{title}</title>{/if}
    <polyline points={shape.line} fill="none" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></polyline>
    <circle cx={shape.last[0]} cy={shape.last[1]} r="2"></circle>
  </svg>
{/if}

<style>
  .spark { flex: none; vertical-align: middle; }
  .spark polyline { stroke: var(--b2s-accent-vivid); }
  .spark circle { fill: var(--b2s-accent-vivid); }
  .spark.is-up polyline { stroke: var(--b2s-color-warning-strong); }
  .spark.is-up circle { fill: var(--b2s-color-warning-strong); }
</style>
