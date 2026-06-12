<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import RemoteConnectorWizardModal from '$lib/components/common/RemoteConnectorWizardModal.svelte';
  import StorageEndpointWizard from '$lib/components/storage-endpoints/StorageEndpointWizard.svelte';

  export let open = false;
  export let onClose: () => void;

  /**
   * Optional props forwarded to the underlying wizard component.
   * Example: { initialZoneId: 12, lockZone: true }
   */
  export let wizardProps: Record<string, any> = {};

  /**
   * Events emitted:
   * - done: { id: number, created_roots?: number, failed_roots?: number }
   */
  const dispatch = createEventDispatcher<{
    done: { id: number; created_roots?: number; failed_roots?: number };
  }>();

  function handleDone(
    e: CustomEvent<{ id: number; created_roots?: number; failed_roots?: number }>
  ) {
    dispatch('done', e.detail);
  }
</script>

<RemoteConnectorWizardModal
  {open}
  onClose={onClose}
  ariaLabelledby="storage-endpoint-wizard-title"
  backdropClass="b2s-modal-backdrop b2s-wizard-backdrop b2s-storage-endpoint-wizard-backdrop"
  modalClass="b2s-modal b2s-wizard-modal b2s-wizard-modal--storage-endpoint is-wizard-modal"
  modalSize="wide"
  WizardComponent={StorageEndpointWizard}
  wizardProps={{ variant: 'modal', ...wizardProps }}
  on:done={handleDone}
/>
