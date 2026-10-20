<script lang="ts">
  import { t } from '$lib/i18n';
  import StorageRootDrawerShell from './StorageRootDrawerShell.svelte';
  import StorageRootAssignedPrincipalCard from './StorageRootAssignedPrincipalCard.svelte';
  import SectionHeaderRow from '../ui/SectionHeaderRow.svelte';
  import ActionFooter from '../ui/ActionFooter.svelte';
  import EmptyState from '../ui/EmptyState.svelte';
  import EntityActionButton from '../entity/EntityActionButton.svelte';

  export let open = false;
  export let onClose: () => void = () => {};
  export let onBrowse: (role: 'guardian') => void = () => {};
  export let onSave: () => void = () => {};
  export let onSelectRoleTab: (role: 'guardian') => void = () => {};
  export let onRemoveOwner: (owner: Record<string, unknown>) => void = () => {};

  export let saving = false;
  export let loading = false;
  export let roleTab: 'guardian' = 'guardian';
  export let draftDirty = false;
  export let canSave = false;
  export let unsavedChangesCount = 0;
  export let selectedRootLabel = t('Storage root');
  export let helperText = '';
  export let browseDisabled = false;
  export let errorMessage: string | null = null;
  export let unresolvedPrincipalLabels: string[] = [];
  export let emptyTitle = t('No guardian assigned yet');
  export let roleRows: Array<Record<string, unknown>> = [];

  export let ownerDisplayName: (owner: Record<string, unknown>) => string = () => 'Unknown';
  export let ownerTypeLabel: (owner: Record<string, unknown>) => string = () => 'User';

  const assignedSectionTitle = () => 'Assigned guardians';

  const unsavedLabel = () =>
    Math.max(1, Math.trunc(unsavedChangesCount || 0)) === 1
      ? '1 unsaved change'
      : t('{value} unsaved changes', { value: (Math.max(1, Math.trunc(unsavedChangesCount || 0))) });
</script>

<StorageRootDrawerShell
  {open}
  {onClose}
  title={t('Guardians')}
  subtitle={selectedRootLabel}
  ariaLabelledby="sr-governance-drawer-title"
  width="660px"
  topOffset="64px"
  rootClass="governance-drawer-shell"
  showFooter={true}
>
  <div class="governance-drawer">
    <div class="governance-drawer__supporting-block">
      <p class="governance-drawer__supporting-line">{t('Manage governance owners')}</p>
    </div>

    <div
      id="sr-governance-assigned-section"
      class="governance-drawer__section"
      role="tabpanel"
      aria-label={t('Assigned guardians')}
    >
      <SectionHeaderRow title={assignedSectionTitle()} count={roleRows.length} compact={true}>
        <svelte:fragment slot="actions">
          <EntityActionButton
            variant="primary"
            icon="bi-search"
            label={t('Browse directory')}
            className="governance-drawer__browse"
            disabled={browseDisabled}
            onClick={() => onBrowse(roleTab)}
          />
        </svelte:fragment>
      </SectionHeaderRow>

      <p class="governance-drawer__helper">{helperText}</p>

      {#if errorMessage}
        <div class="governance-drawer__error" role="status" aria-live="polite">{errorMessage}</div>
      {/if}

      {#if unresolvedPrincipalLabels.length > 0}
        <article class="governance-drawer__warning" role="status" aria-live="polite">
          <strong>
            {t('{unresolvedPrincipalLabelsCount} selected identit{value} not resolved. You can still save resolved assignments.', { unresolvedPrincipalLabelsCount: unresolvedPrincipalLabels.length, value: (unresolvedPrincipalLabels.length > 1 ? 'ies were' : 'y was') })}
          </strong>
          <ul>
            {#each unresolvedPrincipalLabels.slice(0, 6) as label}
              <li>{label}</li>
            {/each}
            {#if unresolvedPrincipalLabels.length > 6}
              <li>{t('+{value} more', { value: (unresolvedPrincipalLabels.length - 6) })}</li>
            {/if}
          </ul>
        </article>
      {/if}

      {#if loading && roleRows.length === 0}
        <div class="governance-drawer__loading" role="status" aria-live="polite">{t('Loading assignments…')}</div>
      {:else if roleRows.length === 0}
        <div class="governance-drawer__empty">
          <EmptyState
            iconClass="bi bi-shield"
            title={emptyTitle}
            description={helperText}
          />
        </div>
      {:else}
        {#if loading}
          <div class="governance-drawer__loading governance-drawer__loading--inline" role="status" aria-live="polite">
            {t('Refreshing assignments…')}
          </div>
        {/if}
        <div class="governance-drawer__list">
          {#each roleRows as owner (`${roleTab}-${Number(owner?.identity_id ?? 0)}`)}
            <StorageRootAssignedPrincipalCard
              {owner}
              role={roleTab}
              {saving}
              {ownerDisplayName}
              {ownerTypeLabel}
              onRemove={onRemoveOwner}
            />
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <svelte:fragment slot="footer">
    <div class="governance-drawer__footer">
      <ActionFooter
        infoText={draftDirty ? unsavedLabel() : null}
        showInfoDot={draftDirty}
      >
        <EntityActionButton variant="secondary" label={t('Cancel')} disabled={saving} onClick={onClose} />
        <EntityActionButton
          variant="primary"
          label={saving ? t('Saving…') : t('Save changes')}
          icon={saving ? 'bi-arrow-repeat' : 'bi-check2'}
          busy={saving}
          disabled={saving || !canSave}
          onClick={onSave}
        />
      </ActionFooter>
    </div>
  </svelte:fragment>
</StorageRootDrawerShell>

<style>
  :global(.governance-drawer-shell .b2s-entity-drawer__header) {
    padding: 28px 32px 0;
    border-bottom: none;
  }

  :global(.governance-drawer-shell .b2s-entity-drawer__header-copy h2) {
    font-size: clamp(1.45rem, 2.2vw, 1.7rem);
    line-height: 1.12;
    letter-spacing: -0.01em;
  }

  :global(.governance-drawer-shell .b2s-entity-drawer__header-copy p) {
    margin-top: 7px;
    font-size: 1rem;
    font-weight: 650;
    color: #22324f;
  }

  :global(.governance-drawer-shell .b2s-entity-drawer__body) {
    padding: 0 0 8px;
  }

  :global(.governance-drawer-shell .b2s-entity-drawer__footer) {
    padding: 16px 32px 24px;
  }

  .governance-drawer {
    padding: 0 32px;
  }

  .governance-drawer__supporting-block {
    margin-top: 6px;
  }

  .governance-drawer__supporting-line {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: #5f6f8b;
  }

  .governance-drawer__section {
    padding-top: 26px;
  }

  :global(.governance-drawer__browse) {
    height: 46px;
    border-radius: 12px;
    padding-inline: 20px;
    white-space: nowrap;
    flex: 0 0 auto;
  }

  .governance-drawer__helper {
    margin: 12px 0 0;
    font-size: 14px;
    line-height: 1.45;
    color: var(--b2s-color-text-muted, #667085);
    max-width: 52ch;
  }

  .governance-drawer__error {
    margin-top: 12px;
    padding: 10px 12px;
    border: 1px solid #f5cbc8;
    border-radius: 10px;
    background: #fff1f1;
    color: #b42318;
    font-size: 13px;
    line-height: 1.45;
  }

  .governance-drawer__warning {
    margin-top: 14px;
    border: 1px solid #f5d08a;
    border-radius: 12px;
    background: #fffaeb;
    color: #8a4b00;
    padding: 12px 14px;
    font-size: 13px;
    line-height: 1.45;
  }

  .governance-drawer__warning strong {
    display: block;
    font-size: 13px;
    font-weight: 700;
  }

  .governance-drawer__warning ul {
    margin: 8px 0 0;
    padding-left: 18px;
  }

  .governance-drawer__loading {
    margin-top: 16px;
    color: var(--b2s-color-text-muted, #667085);
    font-size: 14px;
  }

  .governance-drawer__loading--inline {
    margin-top: 12px;
    font-size: 13px;
  }

  .governance-drawer__empty {
    margin-top: 16px;
  }

  .governance-drawer__list {
    margin-top: 16px;
    display: grid;
    gap: 12px;
    max-height: min(50vh, 560px);
    overflow: auto;
    padding-right: 4px;
  }

  .governance-drawer__footer {
    gap: 16px;
  }

  @media (max-width: 900px) {
    .governance-drawer {
      padding-inline: 20px;
    }

    :global(.governance-drawer__browse) {
      width: 100%;
    }

    .governance-drawer__footer :global(.b2s-action-footer__actions .b2s-btn) {
      width: 100%;
    }
  }
</style>
