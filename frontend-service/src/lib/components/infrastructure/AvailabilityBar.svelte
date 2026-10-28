<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
  import { statusLabel } from '$lib/utils/infrastructure';
  import type { HistoryPoint } from '$lib/api/infrastructure';

  /** Last checks of a component, oldest first (one segment each, empty slots on the left) */
  export let points: HistoryPoint[] = [];
  export let slots = 32;

  $: recent = points.slice(-slots);
  $: padding = Math.max(0, slots - recent.length);
</script>

<div class="avail" role="img" aria-label={t('Availability over the last checks')}>
  {#each Array(padding) as _, i (i)}
    <span class="avail__seg is-empty" title={t('No check')}></span>
  {/each}
  {#each recent as point, i (i)}
    <span
      class={`avail__seg is-${point.status}`}
      title={`${formatDateTime(point.at)} · ${statusLabel(point.status)}${point.latency_ms !== null ? ` · ${point.latency_ms} ms` : ''}`}
    ></span>
  {/each}
</div>

<style>
  .avail {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 2px;
    height: 22px;
    min-width: 120px;
  }

  .avail__seg {
    border-radius: 2px;
    background: #e2e8f0;
  }

  .avail__seg.is-healthy {
    background: #22c55e;
  }

  .avail__seg.is-degraded {
    background: #f59e0b;
  }

  .avail__seg.is-down {
    background: #ef4444;
  }

  .avail__seg.is-unknown {
    background: #cbd5e1;
  }

  .avail__seg.is-empty {
    background: #f1f5f9;
  }
</style>
