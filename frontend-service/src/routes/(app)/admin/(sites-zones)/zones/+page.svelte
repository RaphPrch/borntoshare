<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from "$app/navigation";
  import EmptyState from "$lib/components/ui/EmptyState.svelte";
</script>

<EmptyState
  page
  iconClass="bi bi-diagram-2"
  title={t('No zones yet')}
  description={t('Zones organize governance policies and scope for storage endpoints and storage roots.')}
  ctaLabel={t('Create your first zone')}
  onCta={() => goto('/admin/zones/new')}
  hint={t('You will be guided step by step.')}
/>
