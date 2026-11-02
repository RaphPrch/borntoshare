<script lang="ts">
  import { t } from '$lib/i18n';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import { goto } from '$app/navigation';
</script>

<EmptyState
  page
  iconClass="bi bi-hdd-stack"
  title={t('No storage endpoints yet')}
  description={t('Storage endpoints connect your file servers to discover and govern storage roots.')}
  ctaLabel={t('Add a file server')}
  onCta={() => goto('/admin/storage-endpoints/new')}
/>
