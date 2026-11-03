<script lang="ts">
  import { t } from '$lib/i18n';

  /** The next page of a long list: the same button under every list (a page at a time, never a pager). */
  export let shown: number;
  export let total: number;
  export let page = 50;
  export let onMore: () => void;

  $: left = Math.max(0, total - shown);
</script>

{#if left > 0}
  <div class="b2s-show-more">
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={onMore}>
      {t('Show {count} more ({total} left)', { count: Math.min(page, left), total: left })}
    </button>
  </div>
{/if}

<style>
  .b2s-show-more { display: flex; justify-content: center; padding-top: 10px; }
</style>
