<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityRowCard from '../ui/EntityRowCard.svelte';
  import IconTile from '../ui/IconTile.svelte';
  import { mapPrincipalToDisplayVM } from '../../mappers/principals.mapper';
  import { principalLabel, type PrincipalSearchItem } from '../../utils/principal-search';

  interface Props {
    item: PrincipalSearchItem | undefined;
    selectionKey?: string;
    onRemove?: (key: string) => void;
  }

  let { item, selectionKey = '', onRemove = () => {} }: Props = $props();

  let vm = $derived(mapPrincipalToDisplayVM((item ?? { id: selectionKey, display_name: selectionKey, type: 'other' }) as Record<string, unknown>));
  let removeLabel = $derived(item ? principalLabel(item as Record<string, unknown>) : selectionKey);
</script>

<EntityRowCard
  compact={true}
  className="idb-selected-row"
  title={vm.title}
  subtitle={vm.subtitle}
  tertiary={null}
  typeLabel={vm.typeLabel}
>
  {#snippet icon()}
  
      <IconTile iconClass={vm.iconClass} kind={vm.iconKind} size="sm" />
    
  {/snippet}

  {#snippet actions()}
  
      <button
        type="button"
        class="idb-selected-row__remove"
        aria-label={t('Remove {removeLabel}', { removeLabel })}
        onclick={() => onRemove(selectionKey)}
      >
        <i class="bi bi-x-lg"></i>
      </button>
    
  {/snippet}
</EntityRowCard>

<style>
  .idb-selected-row__remove {
    border: 1px solid var(--idb-border-strong, var(--b2s-color-border));
    border-radius: var(--b2s-radius-pill);
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--idb-panel-bg, #ffffff);
    color: var(--idb-text-muted, var(--b2s-color-text-muted));
    flex: 0 0 24px;
  }

  .idb-selected-row__remove:hover {
    background: var(--idb-hover-bg, var(--b2s-color-surface-muted));
    color: var(--idb-heading, var(--b2s-color-text-strong));
  }
</style>
