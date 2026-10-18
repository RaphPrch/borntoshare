<script lang="ts">
  export let iconClass: string | null = null;
  export let title: string;
  export let description: string | null = null;
  export let ctaLabel: string | null = null;
  export let onCta: (() => void) | null = null;
  export let hint: string | null = null;
  export let containerClass = '';
</script>

<div class={`b2s-empty-state ${containerClass}`.trim()}>
  <div class="empty-card enhanced b2s-empty-card">
    {#if iconClass}
      <div class="empty-icon" aria-hidden="true">
        <i class={iconClass} aria-hidden="true"></i>
      </div>
    {/if}

    <h2>{title}</h2>

    {#if description}
      <p class="empty-description">
        {description}
      </p>
    {/if}

    {#if ctaLabel && onCta}
      <button class="primary large b2s-empty-cta" type="button" on:click={onCta}>
        {ctaLabel}
      </button>
    {/if}

    {#if hint}
      <p class="empty-hint">{hint}</p>
    {/if}
  </div>
</div>
