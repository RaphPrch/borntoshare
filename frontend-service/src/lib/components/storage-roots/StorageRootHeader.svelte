<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityHeader from '$lib/components/entity/EntityHeader.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import type {
    OperationalHeaderMetaItem,
    OperationalHeaderTone
  } from '$lib/components/entity/EntityHeader.svelte';

  type HeaderTone = 'success' | 'warning' | 'error' | 'neutral';

  export let title = t('Storage root');
  export let statusLabel = '';
  export let statusTone: HeaderTone = 'neutral';
  export let showStatusBadge = false;
  export let pathLabel = '—';
  export let rootProbeBusy = false;
  export let selectedStorageRootId: number | null = null;
  export let onRunRootProbe: () => void = () => {};
  export let onNewAccessRequest: () => void = () => {};
  export let onEditRoot: () => void = () => {};
  export let onDeleteRoot: () => void = () => {};

  $: actionsDisabled = !selectedStorageRootId;
  $: resolvedStatusTone = (statusTone === 'error' ? 'danger' : statusTone) as OperationalHeaderTone;
  $: metaItems = [
    { icon: 'bi-folder2-open', label: pathLabel }
  ] satisfies OperationalHeaderMetaItem[];
  $: actions = [
    {
      key: 'probe',
      label: rootProbeBusy ? t('Probe running...') : t('Run probe'),
      icon: rootProbeBusy ? 'bi-arrow-repeat sed-spin' : 'bi-broadcast-pin',
      variant: 'probe',
      disabled: actionsDisabled || rootProbeBusy,
      onClick: onRunRootProbe
    },
    {
      key: 'access-request',
      label: t('New access request'),
      icon: 'bi-plus-lg',
      variant: 'primary',
      disabled: actionsDisabled,
      onClick: onNewAccessRequest
    },
    {
      key: 'edit',
      label: t('Edit storage root'),
      icon: 'bi-pencil-square',
      variant: 'secondary',
      overflow: true,
      disabled: actionsDisabled,
      onClick: onEditRoot
    },
    {
      key: 'delete',
      label: t('Delete storage root'),
      icon: 'bi-trash',
      variant: 'danger',
      overflow: true,
      disabled: actionsDisabled,
      onClick: onDeleteRoot
    }
  ] satisfies EntityActionItem[];
</script>

<EntityHeader
  eyebrow=""
  {title}
  statusLabel={showStatusBadge ? statusLabel : ''}
  statusTone={showStatusBadge ? resolvedStatusTone : 'neutral'}
  {metaItems}
  {actions}
  actionsAriaLabel={t('Storage root actions')}
/>
