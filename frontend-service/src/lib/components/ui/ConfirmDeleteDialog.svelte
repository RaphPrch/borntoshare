<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';

  
  interface Props {
    open?: boolean;
    onClose: () => void;
    onConfirm: () => void;
    ariaLabelledby?: string;
    title?: any;
    description?: string | null;
    impactTitle?: any;
    impactItems?: string[];
    busy?: boolean;
    deleteLabel?: any;
    deleteBusyLabel?: any;
    /** A final deletion: the name of what goes is typed to confirm it (same rule on every screen). */
    confirmName?: string | null;
  }

  let {
    open = false,
    onClose,
    onConfirm,
    ariaLabelledby = 'confirm-delete-dialog-title',
    title = t('Delete item'),
    description = null,
    impactTitle = t('Impact'),
    impactItems = [],
    busy = false,
    deleteLabel = t('Delete'),
    deleteBusyLabel = t('Deleting...'),
    confirmName = null
  }: Props = $props();
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
  requireTextConfirm={Boolean(confirmName)}
  requiredText={confirmName ?? ''}
  textConfirmLabel={t('Type the name to confirm')}
  textConfirmPlaceholder={confirmName ?? ''}
/>
