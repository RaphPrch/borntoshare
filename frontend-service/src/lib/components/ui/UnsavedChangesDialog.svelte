<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';

  
  interface Props {
    /** Asked before a form with unsaved edits closes. */
    open?: boolean;
    onKeepEditing: () => void;
    onDiscard: () => void;
    impact?: string | null;
  }

  let {
    open = false,
    onKeepEditing,
    onDiscard,
    impact = null
  }: Props = $props();
</script>

<ConfirmActionModal
  {open}
  onClose={onKeepEditing}
  onConfirm={onDiscard}
  title={t('Discard unsaved changes')}
  subtitle={t('Your edits have not been saved.')}
  cancelLabel={t('Keep editing')}
  confirmLabel={t('Discard changes')}
  confirmVariant="warning"
  severity="warning"
  impactItems={[impact ?? t('All unsaved edits in this drawer will be lost.')]}
/>
