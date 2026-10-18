<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let availableItems: any[] = [];
  export let selectedItems: any[] = [];

  export let availableTitle = 'Disponibles';
  export let selectedTitle = 'Selected';

  export let getItemKey: (item: any) => string | number = (item: any) => String(item?.id ?? item ?? '');
  export let itemLabel: (item: any) => string = (item: any) => String(item?.label ?? item?.name ?? item ?? '-');

  const dispatch = createEventDispatcher<{ add: { item: any }; remove: { item: any } }>();
</script>

<div class="sr-tags-dual">
  <section class="sr-tags-col">
    <div class="sr-tags-col-head">{availableTitle} ({availableItems.length})</div>
    <div class="sr-tags-col-body">
      {#if availableItems.length === 0}
        <div class="sr-muted">No item available.</div>
      {:else}
        {#each availableItems as item (getItemKey(item))}
          <button type="button" class="sr-tag-transfer-row" on:click={() => dispatch('add', { item })}>
            <slot name="item" {item} side="available">
              <span>{itemLabel(item)}</span>
            </slot>
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
        <div class="sr-muted">No item selected.</div>
      {:else}
        {#each selectedItems as item (getItemKey(item))}
          <button type="button" class="sr-tag-transfer-row selected" on:click={() => dispatch('remove', { item })}>
            <slot name="item" {item} side="selected">
              <span>{itemLabel(item)}</span>
            </slot>
            <span class="sr-tag-transfer-icon">×</span>
          </button>
        {/each}
      {/if}
    </div>
  </section>
</div>

