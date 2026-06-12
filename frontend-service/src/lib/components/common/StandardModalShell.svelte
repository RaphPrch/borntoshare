<script lang="ts">
  import AppModal from '$lib/components/common/AppModal.svelte';
  import ModalActionBar from '$lib/components/common/ModalActionBar.svelte';

  export let open = false;
  export let onClose: () => void;

  export let title = '';
  export let subtitle: string | null = null;
  export let ariaLabelledby = 'standard-modal-title';

  export let backdropClass = 'b2s-modal-backdrop';
  export let modalClass = 'b2s-modal';
  export let bodyClass = 'b2s-standard-modal-body';

  export let showFooter = true;
  export let showClose = true;

  export let cancelLabel = 'Cancel';
  export let confirmLabel = 'Confirm';
  export let confirmBusyLabel: string | null = null;
  export let busy = false;
  export let confirmDisabled = false;
  export let cancelDisabled = false;
  export let confirmVariant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning' = 'primary';

  export let onConfirm: (() => void) | null = null;
</script>

<AppModal
  {open}
  onClose={onClose}
  {backdropClass}
  {modalClass}
  {ariaLabelledby}
  showClose={false}
  wrapContent={false}
>
  <div class="b2s-standard-modal-header">
    <div>
      <h2 id={ariaLabelledby} class="b2s-standard-modal-title">{title}</h2>
      {#if subtitle}
        <p class="b2s-standard-modal-subtitle">{subtitle}</p>
      {/if}
    </div>

    {#if showClose}
      <button class="b2s-standard-modal-close" aria-label="Close" on:click={onClose}>×</button>
    {/if}
  </div>

  <div class={bodyClass}>
    <slot />
  </div>

  {#if showFooter}
    <ModalActionBar
      onCancel={onClose}
      onConfirm={onConfirm ?? onClose}
      {cancelLabel}
      {confirmLabel}
      {confirmBusyLabel}
      {busy}
      {confirmDisabled}
      {cancelDisabled}
      {confirmVariant}
      containerClass="identity-import-actions"
    />
  {/if}
</AppModal>

