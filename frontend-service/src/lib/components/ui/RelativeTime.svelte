<script lang="ts">
  import { formatDateTime, timeAgo } from '$lib/utils/format';

  /**
   * A recent state (last test, last read, seen last): relative (« il y a 5 min »), the exact date on hover.
   * Logs and deadlines keep their absolute date.
   */
  export let value: string | null | undefined;
  export let empty = '—';
</script>

{#if value}<time datetime={value} title={formatDateTime(value)}>{timeAgo(value)}</time>{:else}{empty}{/if}
