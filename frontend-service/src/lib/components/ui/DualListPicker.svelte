<script lang="ts">
  import { t } from '$lib/i18n';



  interface Props {
    availableItems?: any[];
    selectedItems?: any[];
    availableTitle?: any;
    selectedTitle?: any;
    getItemKey?: (item: any) => string | number;
    itemLabel?: (item: any) => string;
    renderItem?: import('svelte').Snippet<[any]>;
    onAdd?: (item: any) => void;
    onRemove?: (item: any) => void;
  }

  let {
    availableItems = [],
    selectedItems = [],
    availableTitle = t('Available'),
    selectedTitle = t('Selected'),
    getItemKey = (item: any) => String(item?.id ?? item ?? ''),
    itemLabel = (item: any) => String(item?.label ?? item?.name ?? item ?? '-'),
    renderItem,
    onAdd,
    onRemove
  }: Props = $props();

</script>

<div class="sr-tags-dual">
  <section class="sr-tags-col">
    <div class="sr-tags-col-head">{availableTitle} ({availableItems.length})</div>
    <div class="sr-tags-col-body">
      {#if availableItems.length === 0}
        <div class="sr-muted">{t('No item available.')}</div>
      {:else}
        {#each availableItems as item (getItemKey(item))}
          <button type="button" class="sr-tag-transfer-row" onclick={() => onAdd?.(item)}>
            {#if renderItem}{@render renderItem({ item, side: "available", })}{:else}
              <span>{itemLabel(item)}</span>
            {/if}
            <span class="sr-tag-transfer-icon">+</span>
          </button>
        {/each}
      {/if}
    </div>
  </section>

  <section class="sr-tags-col">
    <div class="sr-tags-col-head">{selectedTitle} ({selectedItems.length})</div>
    <div class="sr-tags-col-body">
      {#if selectedItems.length === 0}
        <div class="sr-muted">{t('No item selected.')}</div>
      {:else}
        {#each selectedItems as item (getItemKey(item))}
          <button type="button" class="sr-tag-transfer-row selected" onclick={() => onRemove?.(item)}>
            {#if renderItem}{@render renderItem({ item, side: "selected", })}{:else}
              <span>{itemLabel(item)}</span>
            {/if}
            <span class="sr-tag-transfer-icon">×</span>
          </button>
        {/each}
      {/if}
    </div>
  </section>
</div>

