<script lang="ts">
  import { t } from '$lib/i18n';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

  export let onConfigureEndpoint: () => void = () => {};
</script>

<EmptyState
  containerClass="storage-endpoints-empty"
  iconClass="bi bi-hdd-stack"
  title={t('No storage root configured')}
  description={t('To create storage roots, configure at least one storage endpoint first.')}
  ctaLabel={t('Configure a storage endpoint')}
  onCta={onConfigureEndpoint}
  hint={t('The wizard guides you step by step.')}
/>

