<script lang="ts">
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

  export let onConfigureEndpoint: () => void = () => {};
</script>

<EmptyState
  containerClass="storage-endpoints-empty"
  iconClass="bi bi-hdd-stack"
  title="No storage root configured"
  description="To create storage roots, configure at least one storage endpoint first."
  ctaLabel="Configure a storage endpoint"
  onCta={onConfigureEndpoint}
  hint="The wizard guides you step by step."
/>

