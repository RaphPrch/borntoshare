<script lang="ts">
  
  interface Props {
    /**
   * Loading indicator. Inline: spinner + message. In a panel, a list or a detail, a skeleton with the shape of what
   * comes (the message stays for screen readers): `block` and `skeleton="rows"` draw rows, `skeleton="detail"` a card,
   * `skeleton="page"` the tiles of figures then rows (a folder, a 5S screen).
   */
    block?: boolean;
    skeleton?: 'rows' | 'detail' | 'page' | null;
    rows?: number;
    children?: import('svelte').Snippet;
  }

  let {
    block = false,
    skeleton = null,
    rows = 4,
    children
  }: Props = $props();

  let shape = $derived(skeleton ?? (block ? 'rows' : null));
</script>

{#if shape}
  <div class="b2s-skeleton" class:is-detail={shape === 'detail'} role="status" aria-live="polite" aria-busy="true">
    <span class="b2s-visually-hidden">{@render children?.()}</span>
    {#if shape === 'detail'}
      <div class="b2s-skeleton__head"><span class="b2s-skeleton__avatar"></span><span class="b2s-skeleton__line is-title"></span></div>
      <span class="b2s-skeleton__line"></span>
      <span class="b2s-skeleton__line is-short"></span>
      <div class="b2s-skeleton__tiles"><span></span><span></span><span></span></div>
    {:else if shape === 'page'}
      <div class="b2s-skeleton__tiles is-four">
        {#each Array(4) as _, index}<span style="--b2s-skeleton-delay: {index * 70}ms"></span>{/each}
      </div>
      {#each Array(rows) as _, index}
        <div class="b2s-skeleton__row" style="--b2s-skeleton-delay: {280 + index * 90}ms">
          <span class="b2s-skeleton__dot"></span>
          <span class="b2s-skeleton__line" style="width: {78 - (index % 3) * 14}%"></span>
          <span class="b2s-skeleton__line is-tag"></span>
        </div>
      {/each}
    {:else}
      {#each Array(rows) as _, index}
        <div class="b2s-skeleton__row" style="--b2s-skeleton-delay: {index * 90}ms">
          <span class="b2s-skeleton__dot"></span>
          <span class="b2s-skeleton__line" style="width: {78 - (index % 3) * 14}%"></span>
          <span class="b2s-skeleton__line is-tag"></span>
        </div>
      {/each}
    {/if}
  </div>
{:else}
  <div class="b2s-loading" role="status" aria-live="polite">
    <span class="b2s-spinner" aria-hidden="true"></span>
    <span>{@render children?.()}</span>
  </div>
{/if}
