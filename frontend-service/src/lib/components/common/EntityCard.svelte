<script lang="ts">
  export let title = '';
  export let iconClass: string | null = null;
  export let panelClass = '';
  export let headClass = '';
  export let bodyClass = '';
</script>

<article class={`b2s-card ${panelClass}`.trim()}>
  {#if title}
    <div class={`b2s-card__header b2s-entity-card__header ${headClass}`.trim()}>
      <h3 class="b2s-section-title b2s-entity-card__title">
        {#if iconClass}
          <i class={iconClass} aria-hidden="true"></i>
        {/if}
        {title}
      </h3>
      <slot name="actions" />
    </div>
  {/if}

  <div class={`b2s-card__body ${bodyClass}`.trim()}>
    <slot />
  </div>
</article>

<style>
  .b2s-entity-card__title {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: var(--b2s-color-text, #1f2a44);
  }

  .b2s-entity-card__title i {
    color: #2b3b5f;
  }
</style>
