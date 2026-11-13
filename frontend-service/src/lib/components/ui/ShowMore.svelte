<script lang="ts">
  import { t } from '$lib/i18n';

  
  interface Props {
    /** The next page of a long list: the same button under every list (a page at a time, never a pager). */
    shown: number;
    total: number;
    page?: number;
    onMore: () => void;
  }

  let {
    shown,
    total,
    page = 50,
    onMore
  }: Props = $props();

  let left = $derived(Math.max(0, total - shown));
</script>

{#if left > 0}
  <div class="b2s-show-more">
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={onMore}>
      {t('Show {count} more ({total} left)', { count: Math.min(page, left), total: left })}
    </button>
  </div>
{/if}

<style>
  .b2s-show-more { display: flex; justify-content: center; padding-top: 10px; }
</style>
