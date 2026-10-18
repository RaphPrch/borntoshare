<script lang="ts">
  export let cancelLabel = 'Cancel';
  export let confirmLabel = 'Confirm';
  export let confirmBusyLabel: string | null = null;
  export let busy = false;
  export let cancelDisabled = false;
  export let confirmDisabled = false;
  export let confirmVariant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'warning' = 'primary';
  export let containerClass = 'identity-import-actions';
  export let cancelClass = 'b2s-btn b2s-btn-secondary';
  export let confirmClass: string | null = null;

  export let onCancel: () => void;
  export let onConfirm: () => void;
</script>

<footer class={containerClass}>
  <button class={cancelClass} type="button" on:click={onCancel} disabled={busy || cancelDisabled}>
    {cancelLabel}
  </button>
  <button
    class={confirmClass ?? `b2s-btn b2s-btn-${confirmVariant}`}
    type="button"
    on:click={onConfirm}
    disabled={busy || confirmDisabled}
  >
    {busy && confirmBusyLabel ? confirmBusyLabel : confirmLabel}
  </button>
</footer>
