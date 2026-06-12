<script lang="ts">
  import ConfirmActionModal from '$lib/components/common/ConfirmActionModal.svelte';

  export let open = false;
  export let onClose: () => void;
  export let onConfirm: () => void;
  export let ariaLabelledby = 'confirm-delete-dialog-title';
  export let title = 'Delete item';
  export let description: string | null = null;
  export let impactTitle = 'Impact';
  export let impactItems: string[] = [];
  export let busy = false;
  export let deleteLabel = 'Delete';
  export let deleteBusyLabel = 'Deleting...';
  export let requireTextConfirm = false;
  export let requiredText = 'DELETE';
  export let textConfirmLabel = 'Type';
  export let textConfirmPlaceholder = 'DELETE';
</script>

<ConfirmActionModal
  {open}
  {onClose}
  {onConfirm}
  {ariaLabelledby}
  title={title}
  subtitle={description}
  severity="danger"
  confirmVariant="danger"
  cancelLabel="Cancel"
  confirmLabel={deleteLabel}
  confirmBusyLabel={deleteBusyLabel}
  {impactTitle}
  {impactItems}
  {busy}
  {requireTextConfirm}
  {requiredText}
  {textConfirmLabel}
  {textConfirmPlaceholder}
/>
