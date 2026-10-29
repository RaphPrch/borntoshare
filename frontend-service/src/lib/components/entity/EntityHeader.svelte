<script module lang="ts">
  export type OperationalHeaderTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

  export type OperationalHeaderMetaItem = {
    icon?: string;
    label: string;
    tone?: OperationalHeaderTone;
    /** Paths, hosts and codes are shown in monospace */
    mono?: boolean;
  };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

  /**
   * Header card of a selected entity (zone, storage endpoint, storage root):
   * icon, type eyebrow, name, context chips with the status, actions on the right.
   */
  export let iconClass: string | null = null;
  export let eyebrow = '';
  export let title = '';
  export let subtitle = '';
  export let metaItems: OperationalHeaderMetaItem[] = [];
  export let statusLabel = '';
  export let statusTone: OperationalHeaderTone = 'neutral';
  export let showAttention = false;
  export let attentionTitle = t('Attention required');
  export let attentionItems: string[] = [];
  export let attentionMeta: string | null = null;
  export let maxAttentionItems = 2;
  export let containerClass = '';
  // Header buttons: pass `actions`, or fill the "actions" slot for custom content
  export let actions: EntityActionItem[] = [];
  export let actionsAriaLabel = t('Entity actions');

  $: visibleAttentionItems = attentionItems.slice(0, Math.max(1, maxAttentionItems));
  $: hiddenAttentionCount = Math.max(0, attentionItems.length - visibleAttentionItems.length);
</script>

<section class={`b2s-entity-header ${containerClass}`.trim()}>
  <div class="b2s-entity-header__main">
    {#if iconClass}
      <span class="b2s-entity-header__icon" aria-hidden="true"><i class={`bi ${iconClass}`}></i></span>
    {/if}

    <div class="b2s-entity-header__copy">
      {#if eyebrow}<div class="b2s-entity-header__eyebrow">{eyebrow}</div>{/if}
      <h1>{title}</h1>
      {#if subtitle}<p title={subtitle}>{subtitle}</p>{/if}

      {#if metaItems.length > 0 || statusLabel}
        <div class="b2s-entity-header__meta" aria-label={t('Context')}>
          {#each metaItems as item, idx (idx)}
            <span class={`b2s-entity-header__chip is-${item.tone ?? 'neutral'}`} class:is-mono={item.mono}>
              {#if item.icon}<i class={`bi ${item.icon}`} aria-hidden="true"></i>{/if}
              {item.label}
            </span>
          {/each}
          {#if statusLabel}
            <span class={`b2s-entity-header__status is-${statusTone}`}>{statusLabel}</span>
          {/if}
        </div>
      {/if}
    </div>

    <div class="b2s-entity-header__actions">
      {#if $$slots.actions}
        <slot name="actions" />
      {:else if actions.length > 0}
        <EntityActionGroup {actions} ariaLabel={actionsAriaLabel} align="end" />
      {/if}
    </div>
  </div>

  {#if showAttention && attentionItems.length > 0}
    <div class="b2s-entity-header__attention" role="status">
      <i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>
      <div>
        <strong>{attentionTitle}</strong>
        {#if attentionMeta}<span class="b2s-entity-header__attention-meta">{attentionMeta}</span>{/if}
        <ul>
          {#each visibleAttentionItems as item}<li>{item}</li>{/each}
          {#if hiddenAttentionCount > 0}
            <li>{t('{hiddenAttentionCount} more item{value} to review.', { hiddenAttentionCount, value: (hiddenAttentionCount > 1 ? 's' : '') })}</li>
          {/if}
        </ul>
      </div>
    </div>
  {/if}
</section>

<style>
  .b2s-entity-header {
    position: relative;
    z-index: 1;
    display: grid;
    gap: 14px;
    padding: 20px 24px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
    box-shadow: 0 3px 10px rgba(18, 31, 64, 0.04);
  }

  .b2s-entity-header:focus-within {
    z-index: 40;
  }

  .b2s-entity-header__main {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    min-width: 0;
  }

  .b2s-entity-header__icon {
    width: 52px;
    height: 52px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: 14px;
    background: #edf4ff;
    color: var(--b2s-topbar-bg);
    font-size: 22px;
  }

  .b2s-entity-header__copy {
    flex: 1 1 auto;
    min-width: 0;
  }

  .b2s-entity-header__eyebrow {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .b2s-entity-header h1 {
    margin: 2px 0 0;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-xl);
    font-weight: 700;
    line-height: 1.25;
    overflow-wrap: anywhere;
  }

  .b2s-entity-header p {
    margin: 2px 0 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .b2s-entity-header__meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }

  .b2s-entity-header__chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 26px;
    padding: 0 10px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-strong);
    font-size: var(--b2s-fs-xs);
    max-width: 100%;
    overflow-wrap: anywhere;
  }

  .b2s-entity-header__chip.is-mono {
    font-family: var(--b2s-font-mono);
  }

  .b2s-entity-header__chip.is-success { background: #e8f8ef; color: var(--b2s-color-success-strong); }
  .b2s-entity-header__chip.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .b2s-entity-header__chip.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .b2s-entity-header__chip.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }

  .b2s-entity-header__status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 24px;
    padding: 0 10px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
  }

  .b2s-entity-header__status::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: var(--b2s-radius-pill);
    background: currentColor;
  }

  .b2s-entity-header__status.is-success { background: #e8f8ef; border-color: var(--b2s-color-success-border); color: var(--b2s-color-success-strong); }
  .b2s-entity-header__status.is-warning { background: var(--b2s-color-warning-soft); border-color: var(--b2s-color-warning-border); color: var(--b2s-color-warning-strong); }
  .b2s-entity-header__status.is-danger { background: var(--b2s-color-danger-soft); border-color: var(--b2s-color-danger-border); color: var(--b2s-color-danger-strong); }
  .b2s-entity-header__status.is-info { background: var(--b2s-color-info-soft); border-color: var(--b2s-color-info-border); color: var(--b2s-color-info-strong); }

  .b2s-entity-header__actions {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .b2s-entity-header__actions :global(.b2s-action-group) {
    width: auto;
  }

  .b2s-entity-header__attention {
    display: flex;
    gap: 10px;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-warning-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-warning-soft);
    color: #9a3412;
    font-size: var(--b2s-fs-sm);
  }

  .b2s-entity-header__attention-meta {
    margin-left: 8px;
    opacity: 0.8;
  }

  .b2s-entity-header__attention ul {
    margin: 4px 0 0;
    padding-left: 18px;
  }

  @media (max-width: 900px) {
    .b2s-entity-header__main {
      flex-wrap: wrap;
    }

    .b2s-entity-header__actions {
      width: 100%;
    }
  }
</style>
