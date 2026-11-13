<script lang="ts">
  
  interface Props {
    iconClass?: string | null;
    title: string;
    description?: string | null;
    ctaLabel?: string | null;
    onCta?: (() => void) | null;
    hint?: string | null;
    /** The whole page is empty: only this card shows, centred (no file server, no tag, …) */
    page?: boolean;
    containerClass?: string;
  }

  let {
    iconClass = null,
    title,
    description = null,
    ctaLabel = null,
    onCta = null,
    hint = null,
    page = false,
    containerClass = ''
  }: Props = $props();
</script>

<div class={`b2s-empty-state ${page ? 'b2s-empty-page' : ''} ${containerClass}`.replace(/\s+/g, ' ').trim()}>
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
      <button class="b2s-btn b2s-btn-primary b2s-empty-cta" type="button" onclick={onCta}>
        {ctaLabel}
      </button>
    {/if}

    {#if hint}
      <p class="empty-hint">{hint}</p>
    {/if}
  </div>
</div>
