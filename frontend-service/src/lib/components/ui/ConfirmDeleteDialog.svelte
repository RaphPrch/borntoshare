<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';

  export let open = false;
  export let onClose: () => void;
  export let onConfirm: () => void;
  export let ariaLabelledby = 'confirm-delete-dialog-title';
  export let title = t('Delete item');
  export let description: string | null = null;
  export let impactTitle = t('Impact');
  export let impactItems: string[] = [];
  export let busy = false;
  export let deleteLabel = t('Delete');
  export let deleteBusyLabel = t('Deleting...');
  export let requireTextConfirm = false;
  export let requiredText = 'DELETE';
  export let textConfirmLabel = t('Type');
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
  cancelLabel={t('Cancel')}
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
