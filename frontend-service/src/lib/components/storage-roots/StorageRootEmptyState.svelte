<script lang="ts">
  import { t } from '$lib/i18n';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

  
  
  interface Props {
    /** Admins can create; other users only see why the list is empty */
    canManage?: boolean;
    /** A storage root needs a storage endpoint: without one, the action creates the endpoint first */
    hasEndpoints?: boolean;
    onCreateRoot?: () => void;
    onCreateEndpoint?: () => void;
  }

  let {
    canManage = false,
    hasEndpoints = false,
    onCreateRoot = () => {},
    onCreateEndpoint = () => {}
  }: Props = $props();
</script>

<EmptyState
  page
  iconClass="bi bi-folder2-open"
  title={t('No storage roots yet')}
  description={!canManage
    ? t('No storage root is shared with you yet.')
    : hasEndpoints
      ? t('Storage roots are the governed folders that users request access to.')
      : t('Storage roots are discovered on a storage endpoint: create one first.')}
  ctaLabel={!canManage ? null : hasEndpoints ? t('Create your first storage root') : t('Create your first storage endpoint')}
  onCta={hasEndpoints ? onCreateRoot : onCreateEndpoint}
  hint={canManage ? t('You will be guided step by step.') : null}
/>
