<script lang="ts">
  import AppModal from "$lib/components/common/AppModal.svelte";
  import ModalActionBar from "$lib/components/common/ModalActionBar.svelte";

  export let open: boolean;
  export let mode: "create" | "edit" | "delete";

  export let titleCreate: string;
  export let titleEdit: string;
  export let titleDelete: string;
  export let iconClass: string | null = null;

  export let deleteMessage: string;
  export let deleteWarningTitle = "Important";
  export let deleteConsequences: string[] = [];
  export let deleteSafeNotes: string[] = [];

  export let busy = false;
  export let errorMsg: string | null = null;

  export let onClose: () => void;
  export let onSubmit: () => void;
  export let onDelete: () => void;
  export let submitButtonClass = "btn b2s-btn-primary b2s-btn-modal-submit";

  $: title =
    mode === "create"
      ? titleCreate
      : mode === "edit"
      ? titleEdit
      : titleDelete;

  function handleSubmit(event: Event) {
    event.preventDefault();
    if (busy) return;
    if (mode === "delete") {
      onDelete();
      return;
    }
    onSubmit();
  }

  function handleDelete(event: Event) {
    event.preventDefault();
    if (!busy) onDelete();
  }

  const modalId = "entity-form-modal-title";
  $: confirmLabel =
    mode === "delete"
      ? "Delete"
      : mode === "create"
        ? "Create"
        : "Save changes";
  $: confirmBusyLabel =
    mode === "delete"
      ? "Deleting..."
      : mode === "create"
        ? "Creating..."
        : "Saving...";
  $: confirmClass =
    mode === "delete"
      ? "sed-btn sed-btn--danger"
      : submitButtonClass.includes("b2s-btn")
        ? "sed-btn sed-btn--primary"
        : submitButtonClass;
  $: subtitle =
    mode === "delete"
      ? "This action is permanent."
      : mode === "create"
        ? "Define the zone identity and default governance context."
        : "Update the zone identity and default governance context.";
</script>

<AppModal
  {open}
  onClose={onClose}
  modalClass="b2s-modal b2s-modal--md entity-form-modal"
  ariaLabelledby={modalId}
  showClose={false}
  wrapContent={false}
>
  <form class="entity-form-modal__surface" on:submit={handleSubmit}>
    <header class="entity-form-modal__header">
      <div class="entity-form-modal__title-row">
        {#if iconClass}
          <span class="entity-form-modal__icon" aria-hidden="true">
            <i class={iconClass}></i>
          </span>
        {/if}
        <div>
          <h2 id={modalId}>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>

      <button
        type="button"
        class="entity-form-modal__close"
        aria-label="Close"
        on:click={onClose}
      >
        ×
      </button>
    </header>

    <div class="entity-form-modal__body">

      {#if mode === "delete"}
        <div class="entity-form-modal__warning">
          <div class="entity-form-modal__warning-title">
            <i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>
            {deleteWarningTitle}
          </div>

          <p>{deleteMessage}</p>

          {#if deleteConsequences.length}
            <ul>
              {#each deleteConsequences as item}
                <li>{item}</li>
              {/each}
            </ul>
          {/if}

          {#if deleteSafeNotes.length}
            <div class="entity-form-modal__safe-notes">
              <strong>Will NOT be affected:</strong>
              <ul>
                {#each deleteSafeNotes as item}
                  <li>{item}</li>
                {/each}
              </ul>
            </div>
          {/if}
        </div>
      {:else}
        <slot />
      {/if}

      {#if errorMsg}
        <div class="entity-form-modal__error">
          {errorMsg}
        </div>
      {/if}

    </div>

    <ModalActionBar
      onCancel={onClose}
      onConfirm={mode === "delete" ? () => handleDelete(new Event("click")) : () => onSubmit()}
      cancelLabel="Cancel"
      {confirmLabel}
      {confirmBusyLabel}
      {busy}
      confirmVariant={mode === "delete" ? "danger" : "primary"}
      {confirmClass}
      cancelClass="sed-btn sed-btn--secondary"
      containerClass="entity-form-modal__footer"
    />
  </form>
</AppModal>

<style>
  :global(.entity-form-modal) {
    width: min(620px, calc(100vw - 32px));
    overflow: hidden;
  }

  .entity-form-modal__surface {
    display: grid;
    background: #ffffff;
  }

  .entity-form-modal__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
    padding: 22px 24px 16px;
    border-bottom: 1px solid #dde5f1;
    background:
      linear-gradient(135deg, rgba(248, 251, 255, 0.98), rgba(255, 255, 255, 0.96)),
      #ffffff;
  }

  .entity-form-modal__title-row {
    min-width: 0;
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .entity-form-modal__icon {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    border: 1px solid #d7e1f0;
    background: #edf4ff;
    color: var(--b2s-topbar-bg, #111b3f);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .entity-form-modal__header h2 {
    margin: 0;
    color: #10203f;
    font-size: 1.35rem;
    line-height: 1.15;
    font-weight: 760;
  }

  .entity-form-modal__header p {
    margin: 4px 0 0;
    color: #64748b;
    font-size: 0.9rem;
    font-weight: 600;
  }

  .entity-form-modal__close {
    width: 36px;
    height: 36px;
    border: 1px solid transparent;
    border-radius: 10px;
    background: transparent;
    color: #64748b;
    font-size: 24px;
    line-height: 1;
  }

  .entity-form-modal__close:hover {
    border-color: #d7e1f0;
    background: #f5f8fd;
    color: #0f172a;
  }

  .entity-form-modal__body {
    padding: 20px 24px 22px;
    display: grid;
    gap: 14px;
  }

  .entity-form-modal__warning {
    border: 1px solid #efd39c;
    border-radius: 14px;
    background: #fff8ea;
    color: #684a1e;
    padding: 14px;
    display: grid;
    gap: 10px;
  }

  .entity-form-modal__warning-title {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #995f00;
    font-weight: 760;
  }

  .entity-form-modal__warning p,
  .entity-form-modal__warning ul {
    margin: 0;
  }

  .entity-form-modal__safe-notes {
    display: grid;
    gap: 6px;
    color: #5f513f;
    font-size: 0.9rem;
  }

  .entity-form-modal__error {
    border: 1px solid #f1c7ce;
    border-radius: 12px;
    background: #fff1f3;
    color: #a4373d;
    padding: 10px 12px;
    font-size: 0.9rem;
    font-weight: 700;
  }

  .entity-form-modal__footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding: 14px 24px 20px;
    border-top: 1px solid #dde5f1;
    background: #f8fbff;
  }

  @media (max-width: 620px) {
    .entity-form-modal__header,
    .entity-form-modal__body,
    .entity-form-modal__footer {
      padding-left: 16px;
      padding-right: 16px;
    }

    .entity-form-modal__footer {
      flex-direction: column-reverse;
      align-items: stretch;
    }
  }
</style>
