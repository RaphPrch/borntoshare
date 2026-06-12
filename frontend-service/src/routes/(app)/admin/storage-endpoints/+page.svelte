<script lang="ts">
  import { goto, invalidateAll } from '$app/navigation';
  import EmptyStateCard from '$lib/components/common/EmptyStateCard.svelte';
  import StorageEndpointWizardModal from '$lib/components/storage-endpoints/StorageEndpointWizardModal.svelte';
  import { toast } from '$lib/utils/toast';

  export let data: {
    endpoints: any[];
  };

  let showWizard = false;
  $: hasEndpoints = Array.isArray(data?.endpoints) && data.endpoints.length > 0;
</script>

{#if !hasEndpoints}
  <EmptyStateCard
    containerClass="storage-endpoints-empty"
    iconClass="bi bi-hdd-stack"
    title="No storage endpoints yet"
    description="Storage endpoints are required to discover storage roots, apply governance rules and manage access requests."
    ctaLabel="Create your first storage endpoint"
    onCta={() => (showWizard = true)}
    hint="The wizard will guide you step by step."
  />
{/if}

<StorageEndpointWizardModal
  open={showWizard}
  onClose={() => (showWizard = false)}
  on:done={async () => {
    showWizard = false;
    toast.success('Storage endpoint created.');
    await invalidateAll();
    await goto('/admin/storage-endpoints');
  }}
/>
