<script lang="ts">
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import Drawer from "$lib/components/ui/Drawer.svelte";
  import EntityActionButton from "$lib/components/entity/EntityActionButton.svelte";
  import ZoneFormFields from "$lib/components/zones/ZoneFormFields.svelte";

  import type { ZoneOverview } from "$lib/api/zones";

  export let open: boolean;
  export let zone: ZoneOverview | null;
  export let mode: "create" | "edit" | "delete";

  export let onClose: () => void;
  export let onSubmit: (payload: any) => Promise<void> | void;
  export let onDelete: () => Promise<void> | void;

  let form = {
    name: "",
    code: "",
    description: "",
  };

  let busy = false;
  let errorMsg: string | null = null;

  $: if (mode === "create") {
    errorMsg = null;
    form = {
      name: "",
      code: "",
      description: "",
    };
  }

  $: if (zone && mode !== "create") {
    errorMsg = null;
    form = {
      name: zone.name ?? "",
      code: zone.code ?? "",
      description: zone.description ?? "",
    };
  }

  $: drawerTitle =
    mode === "create"
      ? t('Create zone')
      : mode === "edit"
        ? t('Edit zone')
        : t('Delete zone');
  $: drawerSubtitle =
    mode === "delete"
      ? t('This action is permanent.')
      : mode === "create"
        ? t('Define the zone identity and default governance context.')
        : t('Update the zone identity and default governance context.');
  $: confirmLabel =
    mode === "delete"
      ? t('Delete')
      : mode === "create"
        ? t('Create')
        : t('Save changes');
  $: busyLabel =
    mode === "delete"
      ? t('Deleting...')
      : mode === "create"
        ? t('Creating...')
        : t('Saving...');

  async function submit() {
    errorMsg = null;

    busy = true;
    try {
      await onSubmit({
        ...form,
        code: form.code?.trim() || null,
        description: form.description?.trim() || null,
      });
    } catch (e) {
      errorMsg = e?.message ?? t('Operation failed');
    } finally {
      busy = false;
    }
  }

  async function confirmDelete() {
    errorMsg = null;
    busy = true;

    try {
      await onDelete();
    } catch (e) {
      errorMsg = e?.message ?? t('Delete failed');
    } finally {
      busy = false;
    }
  }

  const confirm = () => {
    if (busy) return;
    if (mode === "delete") {
      void confirmDelete();
      return;
    }
    void submit();
  };
</script>

<Drawer
  closeOnBackdrop={false}
  closeOnEscape={false}
  {open}
  title={drawerTitle}
  subtitle={drawerSubtitle}
  iconClass="bi bi-diagram-2"
  onClose={onClose}
  ariaLabelledby="zone-form-drawer-title"
  rootClass="zone-form-drawer"
  showFooter={true}
>
  <div class="zone-form-drawer__content">
    {#if mode === "delete"}
      <InlineAlert tone="warning" title={t('Deleting a zone has consequences')} class="zone-form-drawer__warning">
        <p>{t('Deleting this zone is irreversible.')}</p>

        <ul>
          <li>{t('The zone will be permanently removed')}</li>
          <li>{t('Associated links will be deleted')}</li>
        </ul>

        <div class="zone-form-drawer__safe-notes">
          <strong>{t('Will NOT be affected:')}</strong>
          <ul>
            <li>{t('No storage data will be modified')}</li>
          </ul>
        </div>
      </InlineAlert>
    {:else}
      <ZoneFormFields bind:form mode={mode} />
    {/if}

    {#if errorMsg}
      <InlineAlert tone="error">{errorMsg}</InlineAlert>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="zone-form-drawer__actions">
      <EntityActionButton variant="secondary" label={t('Cancel')} disabled={busy} onClick={onClose} />
      <EntityActionButton
        variant={mode === "delete" ? "danger" : "primary"}
        icon={busy ? "bi-arrow-repeat" : mode === "delete" ? "bi-trash" : "bi-check2"}
        busy={busy}
        label={busy ? busyLabel : confirmLabel}
        disabled={busy}
        onClick={confirm}
      />
    </div>
  </svelte:fragment>
</Drawer>

<style>
  .zone-form-drawer__content {
    display: grid;
    gap: 14px;
  }

  .zone-form-drawer__content :global(.zone-form-drawer__warning .b2s-inline-alert__text) {
    display: grid;
    gap: 10px;
  }

  .zone-form-drawer__content :global(.zone-form-drawer__warning p),
  .zone-form-drawer__content :global(.zone-form-drawer__warning ul) {
    margin: 0;
  }

  .zone-form-drawer__safe-notes {
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    padding: 10px 12px;
    color: var(--b2s-color-text-soft);
  }

  .zone-form-drawer__safe-notes strong {
    display: block;
    margin-bottom: 6px;
    color: var(--b2s-color-text-strong);
  }

  .zone-form-drawer__actions {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    flex-wrap: wrap;
  }
</style>
