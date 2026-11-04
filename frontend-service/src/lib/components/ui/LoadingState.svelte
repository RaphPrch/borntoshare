<script lang="ts">
  /**
   * Loading indicator. Inline: spinner + message. In a panel, a list or a detail, a skeleton with the shape of what
   * comes (the message stays for screen readers): `block` and `skeleton="rows"` draw rows, `skeleton="detail"` a card.
   */
  export let block = false;
  export let skeleton: 'rows' | 'detail' | null = null;
  export let rows = 4;

  $: shape = skeleton ?? (block ? 'rows' : null);
</script>

{#if shape}
  <div class="b2s-skeleton" class:is-detail={shape === 'detail'} role="status" aria-live="polite" aria-busy="true">
    <span class="b2s-visually-hidden"><slot /></span>
    {#if shape === 'detail'}
      <div class="b2s-skeleton__head"><span class="b2s-skeleton__avatar"></span><span class="b2s-skeleton__line is-title"></span></div>
      <span class="b2s-skeleton__line"></span>
      <span class="b2s-skeleton__line is-short"></span>
      <div class="b2s-skeleton__tiles"><span></span><span></span><span></span></div>
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
    <span><slot /></span>
  </div>
{/if}
