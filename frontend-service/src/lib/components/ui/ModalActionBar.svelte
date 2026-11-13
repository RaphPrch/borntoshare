<script lang="ts">
  import { t } from '$lib/i18n';

  interface Props {
    cancelLabel?: any;
    confirmLabel?: any;
    confirmBusyLabel?: string | null;
    busy?: boolean;
    cancelDisabled?: boolean;
    confirmDisabled?: boolean;
    confirmVariant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning';
    containerClass?: string;
    cancelClass?: string;
    confirmClass?: string | null;
    onCancel: () => void;
    onConfirm: () => void;
  }

  let {
    cancelLabel = t('Cancel'),
    confirmLabel = t('Confirm'),
    confirmBusyLabel = null,
    busy = false,
    cancelDisabled = false,
    confirmDisabled = false,
    confirmVariant = 'primary',
    containerClass = 'identity-import-actions',
    cancelClass = 'b2s-btn b2s-btn-secondary',
    confirmClass = null,
    onCancel,
    onConfirm
  }: Props = $props();
</script>

<footer class={containerClass}>
  <button class={cancelClass} type="button" onclick={onCancel} disabled={busy || cancelDisabled}>
    {cancelLabel}
  </button>
  <button
    class={confirmClass ?? `b2s-btn b2s-btn-${confirmVariant}`}
    type="button"
    onclick={onConfirm}
    disabled={busy || confirmDisabled}
  >
    {busy && confirmBusyLabel ? confirmBusyLabel : confirmLabel}
  </button>
</footer>
