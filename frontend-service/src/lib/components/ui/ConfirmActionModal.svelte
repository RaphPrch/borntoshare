<script lang="ts">

  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import ModalActionBar from '$lib/components/ui/ModalActionBar.svelte';





  interface Props {
    open?: boolean;
    onClose: () => void;
    onConfirm: () => void;
    ariaLabelledby?: string;
    role?: 'dialog' | 'alertdialog';
    backdropClass?: string;
    modalClass?: string | null;
    severity?: 'warning' | 'danger';
    title?: any;
    subtitle?: string | null;
    impactTitle?: any;
    impactItems?: string[];
    cancelLabel?: any;
    confirmLabel?: any;
    confirmBusyLabel?: string | null;
    busy?: boolean;
    confirmVariant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning' | null;
    actionsClass?: string;
    cancelClass?: string;
    confirmClass?: string | null;
    requireTextConfirm?: boolean;
    requiredText?: string;
    textConfirmLabel?: any;
    textConfirmPlaceholder?: string;
    children?: import('svelte').Snippet;
  }

  let {
    open = false,
    onClose,
    onConfirm,
    ariaLabelledby = 'confirm-action-modal-title',
    role = 'alertdialog',
    backdropClass = 'b2s-modal-backdrop',
    modalClass = null,
    severity = 'danger',
    title = t('Confirm action'),
    subtitle = null,
    impactTitle = t('Impact'),
    impactItems = [],
    cancelLabel = t('Cancel'),
    confirmLabel = t('Confirm'),
    confirmBusyLabel = null,
    busy = false,
    confirmVariant = null,
    actionsClass = 'b2s-confirm-actions',
    cancelClass = 'b2s-btn b2s-btn-secondary',
    confirmClass = null,
    requireTextConfirm = false,
    requiredText = '',
    textConfirmLabel = t('Type confirmation text'),
    textConfirmPlaceholder = 'Type text',
    children
  }: Props = $props();

  let typedConfirm = $state('');
  let normalizedTyped = $derived(typedConfirm.trim());
  let textConfirmValid = $derived(!requireTextConfirm || normalizedTyped === requiredText);
  let resolvedConfirmVariant = $derived(confirmVariant ?? (severity === 'danger' ? 'danger' : 'warning'));
  let resolvedModalClass = $derived(modalClass ?? `b2s-modal b2s-confirm-modal b2s-confirm-modal--${severity}`);
  let confirmDisabled = $derived(!textConfirmValid);

  $effect(() => {
    if (!open) {
      typedConfirm = '';
    }
  });
</script>

<AppModal
  {open}
  onClose={onClose}
  {backdropClass}
  modalClass={resolvedModalClass}
  size="md"
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

    {@render children?.()}

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
