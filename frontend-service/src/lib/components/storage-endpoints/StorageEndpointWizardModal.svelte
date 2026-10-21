<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import StorageEndpointWizard from '$lib/components/storage-endpoints/StorageEndpointWizard.svelte';

  export let open = false;
  export let onClose: () => void;

  /**
   * Optional props forwarded to the wizard.
   * Example: { initialZoneId: 12, lockZone: true }
   */
  export let wizardProps: { initialZoneId?: number | null; lockZone?: boolean } = {};

  /** done: { id: number, created_roots?: number, failed_roots?: number } */
  const dispatch = createEventDispatcher<{
    done: { id: number; created_roots?: number; failed_roots?: number };
  }>();

  function handleDone(e: CustomEvent<{ id: number; created_roots?: number; failed_roots?: number }>) {
    dispatch('done', e.detail);
    onClose();
  }
</script>

<!-- Mounted only while open so each opening starts from a clean state -->
{#if open}
  <StorageEndpointWizard open {onClose} {...wizardProps} on:done={handleDone} />
{/if}
