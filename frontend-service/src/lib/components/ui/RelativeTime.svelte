<script lang="ts">
  import { formatDateTime, timeAgo } from '$lib/utils/format';

  
  interface Props {
    /**
   * A recent state (last test, last read, seen last): relative (« il y a 5 min »), the exact date on hover.
   * Logs and deadlines keep their absolute date.
   */
    value: string | null | undefined;
    empty?: string;
  }

  let { value, empty = '—' }: Props = $props();
</script>

{#if value}<time datetime={value} title={formatDateTime(value)}>{timeAgo(value)}</time>{:else}{empty}{/if}
