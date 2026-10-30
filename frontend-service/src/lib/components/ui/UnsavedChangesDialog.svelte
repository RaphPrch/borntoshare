<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';

  /** Asked before a form with unsaved edits closes. */
  export let open = false;
  export let onKeepEditing: () => void;
  export let onDiscard: () => void;
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
  impactItems={[t('All unsaved edits in this drawer will be lost.')]}
/>
