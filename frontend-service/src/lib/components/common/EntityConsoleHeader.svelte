<script lang="ts">
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/common/EntityActionGroup.svelte';
  import EntityOperationalHeader, {
    type OperationalHeaderMetaItem,
    type OperationalHeaderTone
  } from '$lib/components/common/EntityOperationalHeader.svelte';

  export let eyebrow = '';
  export let title = '';
  export let subtitle = '';
  export let metaItems: OperationalHeaderMetaItem[] = [];
  export let statusLabel = 'Unknown';
  export let statusTone: OperationalHeaderTone = 'neutral';
  export let statusIconClass: string | null = null;
  export let showAttention = false;
  export let attentionTitle = 'Attention required';
  export let attentionItems: string[] = [];
  export let attentionMeta: string | null = null;
  export let attentionIconClass = 'bi bi-exclamation-triangle-fill';
  export let maxAttentionItems = 2;
  export let containerClass = '';
  export let actions: EntityActionItem[] = [];
  export let actionsAriaLabel = 'Entity actions';
  export let actionsAlign: 'start' | 'end' = 'end';
</script>

<EntityOperationalHeader
  {eyebrow}
  {title}
  {subtitle}
  {metaItems}
  {statusLabel}
  {statusTone}
  {statusIconClass}
  {showAttention}
  {attentionTitle}
  {attentionItems}
  {attentionMeta}
  {attentionIconClass}
  {maxAttentionItems}
  {containerClass}
>
  <svelte:fragment slot="actions">
    {#if $$slots.actions}
      <slot name="actions" />
    {:else if actions.length > 0}
      <EntityActionGroup actions={actions} ariaLabel={actionsAriaLabel} align={actionsAlign} />
    {/if}
  </svelte:fragment>
</EntityOperationalHeader>
