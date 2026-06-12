<script lang="ts">
  import AppModal from '$lib/components/common/AppModal.svelte';
  import ModalActionBar from '$lib/components/common/ModalActionBar.svelte';

  export let open = false;
  export let onClose: () => void;
  export let onConfirm: () => void;

  export let ariaLabelledby = 'confirm-action-modal-title';
  export let role: 'dialog' | 'alertdialog' = 'alertdialog';
  export let backdropClass = 'b2s-modal-backdrop';
  export let modalClass: string | null = null;
  export let severity: 'warning' | 'danger' = 'danger';

  export let title = 'Confirm action';
  export let subtitle: string | null = null;
  export let impactTitle = 'Impact';
  export let impactItems: string[] = [];

  export let cancelLabel = 'Cancel';
  export let confirmLabel = 'Confirm';
  export let confirmBusyLabel: string | null = null;
  export let busy = false;
  export let confirmVariant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning' | null = null;
  export let actionsClass = 'b2s-confirm-actions';
  export let cancelClass = 'sed-btn sed-btn--secondary';
  export let confirmClass: string | null = null;

  export let requireTextConfirm = false;
  export let requiredText = 'DELETE';
  export let textConfirmLabel = 'Type confirmation text';
  export let textConfirmPlaceholder = 'Type text';

  let typedConfirm = '';
  $: normalizedTyped = typedConfirm.trim();
  $: textConfirmValid = !requireTextConfirm || normalizedTyped === requiredText;
  $: resolvedConfirmVariant = confirmVariant ?? (severity === 'danger' ? 'danger' : 'warning');
  $: resolvedModalClass = modalClass ?? `b2s-modal b2s-confirm-modal b2s-confirm-modal--${severity}`;
  $: confirmDisabled = !textConfirmValid;

  $: if (!open) {
    typedConfirm = '';
  }
</script>

<AppModal
  {open}
  onClose={onClose}
  {backdropClass}
  modalClass={resolvedModalClass}
  {ariaLabelledby}
  {role}
>
  <div class="b2s-confirm-head">
    <h3 id={ariaLabelledby}>{title}</h3>
    {#if subtitle}
      <p>{subtitle}</p>
    {/if}
  </div>

  <div class="b2s-confirm-body">
    {#if impactItems.length > 0}
      <div class="b2s-confirm-impact" aria-live="polite">
        <div class="b2s-confirm-impact-title">{impactTitle}</div>
        <ul>
          {#each impactItems as impact}
            <li>{impact}</li>
          {/each}
        </ul>
      </div>
    {/if}

    <slot />

    {#if requireTextConfirm}
      <label class="b2s-confirm-input-wrap">
        <span>{textConfirmLabel} <strong>{requiredText}</strong></span>
        <input
          class="b2s-input"
          type="text"
          bind:value={typedConfirm}
          placeholder={textConfirmPlaceholder}
          autocomplete="off"
          spellcheck="false"
        />
      </label>
    {/if}
  </div>

  <ModalActionBar
    onCancel={onClose}
    {onConfirm}
    {cancelLabel}
    {confirmLabel}
    {confirmBusyLabel}
    {busy}
    confirmVariant={resolvedConfirmVariant}
    {confirmDisabled}
    containerClass={actionsClass}
    {cancelClass}
    {confirmClass}
  />
</AppModal>
