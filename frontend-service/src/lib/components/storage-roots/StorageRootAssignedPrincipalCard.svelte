<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityRowCard from '../ui/EntityRowCard.svelte';
  import IconTile from '../ui/IconTile.svelte';
  import { mapGovernanceOwnerToCardVM } from '../../mappers/governance-owners.mapper';

  export let owner: Record<string, unknown> = {};
  export let role: 'guardian' = 'guardian';
  export let saving = false;
  export let removeLocked = false;
  export let ownerDisplayName: (owner: Record<string, unknown>) => string = () => t('Unknown');
  export let ownerTypeLabel: (owner: Record<string, unknown>) => string = () => t('User');
  export let onRemove: (owner: Record<string, unknown>) => void = () => {};

  $: vm = mapGovernanceOwnerToCardVM(owner, {
    displayName: ownerDisplayName(owner),
    typeLabel: ownerTypeLabel(owner)
  });
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
    <svelte:fragment slot="icon">
      <IconTile iconClass={vm.iconClass} kind={vm.iconKind} />
    </svelte:fragment>

    <svelte:fragment slot="actions">
      <button
        type="button"
        class="assigned-principal-card__remove"
        on:click={() => onRemove(owner)}
        disabled={saving || removeLocked}
        aria-label={t('Remove {role}', { role: t('guardian') })}
        title={removeLocked ? t('You cannot remove yourself: another guardian or an administrator does it.') : t('Remove {role}', { role: t('guardian') })}
      >
        <i class="bi bi-x-lg"></i>
      </button>
    </svelte:fragment>
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
