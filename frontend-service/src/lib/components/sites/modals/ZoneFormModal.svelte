<script lang="ts">
  import EntityDrawerShell from "$lib/components/common/EntityDrawerShell.svelte";
  import EntityActionButton from "$lib/components/common/EntityActionButton.svelte";
  import ZoneFormFields from "$lib/components/common/ZoneFormFields.svelte";

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
      ? "Create zone"
      : mode === "edit"
        ? "Edit zone"
        : "Delete zone";
  $: drawerSubtitle =
    mode === "delete"
      ? "This action is permanent."
      : mode === "create"
        ? "Define the zone identity and default governance context."
        : "Update the zone identity and default governance context.";
  $: confirmLabel =
    mode === "delete"
      ? "Delete"
      : mode === "create"
        ? "Create"
        : "Save changes";
  $: busyLabel =
    mode === "delete"
      ? "Deleting..."
      : mode === "create"
        ? "Creating..."
        : "Saving...";

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
      errorMsg = e?.message ?? "Operation failed";
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
      errorMsg = e?.message ?? "Delete failed";
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

<EntityDrawerShell
  {open}
  title={drawerTitle}
  subtitle={drawerSubtitle}
  iconClass="bi bi-diagram-2"
  onClose={onClose}
  ariaLabelledby="zone-form-drawer-title"
  width="560px"
  topOffset="70px"
  rootClass="zone-form-drawer"
  showFooter={true}
>
  <div class="zone-form-drawer__content">
    {#if mode === "delete"}
      <div class="zone-form-drawer__warning">
        <div class="zone-form-drawer__warning-title">
          <i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>
          Deleting a zone has consequences
        </div>

        <p>Deleting this zone is irreversible.</p>

        <ul>
          <li>The zone will be permanently removed</li>
          <li>Associated links will be deleted</li>
        </ul>

        <div class="zone-form-drawer__safe-notes">
          <strong>Will NOT be affected:</strong>
          <ul>
            <li>No storage data will be modified</li>
          </ul>
        </div>
      </div>
    {:else}
      <ZoneFormFields bind:form mode={mode} />
    {/if}

    {#if errorMsg}
      <div class="zone-form-drawer__error">
        {errorMsg}
      </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="zone-form-drawer__actions">
      <EntityActionButton compact={true} variant="secondary" label="Cancel" disabled={busy} onClick={onClose} />
      <EntityActionButton
        compact={true}
        variant={mode === "delete" ? "danger" : "primary"}
        icon={busy ? "bi-arrow-repeat" : mode === "delete" ? "bi-trash" : "bi-check2"}
        busy={busy}
        label={busy ? busyLabel : confirmLabel}
        disabled={busy}
        onClick={confirm}
      />
    </div>
  </svelte:fragment>
</EntityDrawerShell>

<style>
  .zone-form-drawer__content {
    display: grid;
    gap: 14px;
  }

  .zone-form-drawer__warning {
    border: 1px solid #efd39c;
    border-radius: 14px;
    background: #fff8ea;
    color: #684a1e;
    padding: 14px;
    display: grid;
    gap: 10px;
  }

  .zone-form-drawer__warning-title {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #995f00;
    font-weight: 760;
  }

  .zone-form-drawer__warning p,
  .zone-form-drawer__warning ul {
    margin: 0;
  }

  .zone-form-drawer__safe-notes {
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.7);
    padding: 10px 12px;
    color: #475569;
  }

  .zone-form-drawer__safe-notes strong {
    display: block;
    margin-bottom: 6px;
    color: #334155;
  }

  .zone-form-drawer__error {
    border: 1px solid #f0c1c1;
    border-radius: 12px;
    background: #fff5f5;
    color: #a12e2e;
    padding: 10px 12px;
    font-weight: 650;
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
