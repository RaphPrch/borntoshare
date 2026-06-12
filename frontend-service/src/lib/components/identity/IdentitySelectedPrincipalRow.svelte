<script lang="ts">
  import EntityRowCard from '../ui/EntityRowCard.svelte';
  import IconTile from '../ui/IconTile.svelte';
  import { mapPrincipalToDisplayVM } from '../../services/mappers/principals.mapper';
  import { principalLabel, type PrincipalSearchItem } from '../../utils/principal-search';

  export let item: PrincipalSearchItem | undefined;
  export let selectionKey = '';
  export let onRemove: (key: string) => void = () => {};

  $: vm = mapPrincipalToDisplayVM((item ?? { id: selectionKey, display_name: selectionKey, type: 'other' }) as Record<string, unknown>);
  $: removeLabel = item ? principalLabel(item as Record<string, unknown>) : selectionKey;
</script>

<EntityRowCard
  compact={true}
  className="idb-selected-row"
  title={vm.title}
  subtitle={vm.subtitle}
  tertiary={null}
  typeLabel={vm.typeLabel}
>
  <svelte:fragment slot="icon">
    <IconTile iconClass={vm.iconClass} kind={vm.iconKind} size="sm" />
  </svelte:fragment>

  <svelte:fragment slot="actions">
    <button
      type="button"
      class="idb-selected-row__remove"
      aria-label={`Remove ${removeLabel}`}
      on:click={() => onRemove(selectionKey)}
    >
      <i class="bi bi-x-lg"></i>
    </button>
  </svelte:fragment>
</EntityRowCard>

<style>
  .idb-selected-row__remove {
    border: 1px solid var(--idb-border-strong, #d6deeb);
    border-radius: 999px;
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--idb-panel-bg, #ffffff);
    color: var(--idb-text-muted, #6b7f98);
    flex: 0 0 24px;
  }

  .idb-selected-row__remove:hover {
    background: var(--idb-hover-bg, #f3f7fc);
    color: var(--idb-heading, #20324d);
  }
</style>
