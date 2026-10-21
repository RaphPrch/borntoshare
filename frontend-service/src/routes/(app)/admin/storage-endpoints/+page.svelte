<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto, invalidateAll } from '$app/navigation';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import StorageEndpointWizardModal from '$lib/components/storage-endpoints/StorageEndpointWizardModal.svelte';
  import { toast } from '$lib/stores/toast';

  export let data: {
    endpoints: any[];
  };

  let showWizard = false;
  $: hasEndpoints = Array.isArray(data?.endpoints) && data.endpoints.length > 0;
</script>

{#if !hasEndpoints}
  <EmptyState
    containerClass="storage-endpoints-empty"
    iconClass="bi bi-hdd-stack"
    title={t('No storage endpoints yet')}
    description={t('Storage endpoints connect your file servers to discover and govern storage roots.')}
    ctaLabel={t('Create your first storage endpoint')}
    onCta={() => (showWizard = true)}
    hint={t('You will be guided step by step.')}
  />
{/if}

<StorageEndpointWizardModal
  open={showWizard}
  onClose={() => (showWizard = false)}
  on:done={async () => {
    showWizard = false;
    toast.success(t('Storage endpoint created.'));
    await invalidateAll();
    await goto('/admin/storage-endpoints');
  }}
/>
