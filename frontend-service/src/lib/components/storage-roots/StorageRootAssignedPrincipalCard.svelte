<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityRowCard from '../ui/EntityRowCard.svelte';
  import IconTile from '../ui/IconTile.svelte';
  import { mapGovernanceOwnerToCardVM } from '../../mappers/governance-owners.mapper';

  interface Props {
    owner?: Record<string, unknown>;
    saving?: boolean;
    removeLocked?: boolean;
    ownerDisplayName?: (owner: Record<string, unknown>) => string;
    ownerTypeLabel?: (owner: Record<string, unknown>) => string;
    onRemove?: (owner: Record<string, unknown>) => void;
  }

  let {
    owner = {},
    saving = false,
    removeLocked = false,
    ownerDisplayName = () => t('Unknown'),
    ownerTypeLabel = () => t('User'),
    onRemove = () => {}
  }: Props = $props();

  let vm = $derived(mapGovernanceOwnerToCardVM(owner, {
    displayName: ownerDisplayName(owner),
    typeLabel: ownerTypeLabel(owner)
  }));
</script>

<div
  class="assigned-principal-card__row"
  data-governance-owner-row
  data-owner-identity-id={String(Number(owner?.identity_id ?? 0) || '')}
  data-owner-display={vm.title}
>
  <EntityRowCard
    title={vm.title}
    subtitle={vm.subtitle}
    tertiary={vm.tertiary}
    typeLabel={vm.typeLabel}
  >
    {#snippet icon()}
      
        <IconTile iconClass={vm.iconClass} kind={vm.iconKind} />
      
      {/snippet}

    {#snippet actions()}
      
        <button
          type="button"
          class="assigned-principal-card__remove"
          onclick={() => onRemove(owner)}
          disabled={saving || removeLocked}
          aria-label={t('Remove {role}', { role: t('guardian') })}
          title={removeLocked ? t('You cannot remove yourself: another guardian or an administrator does it.') : t('Remove {role}', { role: t('guardian') })}
        >
          <i class="bi bi-x-lg"></i>
        </button>
      
      {/snippet}
  </EntityRowCard>
</div>

<style>
  .assigned-principal-card__remove {
    width: 34px;
    height: 34px;
    border: none;
    border-radius: var(--b2s-radius-pill);
    background: #eef2f8;
    color: var(--b2s-color-text-muted);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .assigned-principal-card__remove:hover {
    background: #e4e9f2;
    color: #344054;
  }
</style>
