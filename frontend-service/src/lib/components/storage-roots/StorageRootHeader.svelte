<script lang="ts">
  import EntityConsoleHeader from '$lib/components/common/EntityConsoleHeader.svelte';
  import type { EntityActionItem } from '$lib/components/common/EntityActionGroup.svelte';
  import type {
    OperationalHeaderMetaItem,
    OperationalHeaderTone
  } from '$lib/components/common/EntityOperationalHeader.svelte';

  type HeaderTone = 'success' | 'warning' | 'error' | 'neutral';

  export let title = 'Storage root';
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
      label: rootProbeBusy ? 'Probe running...' : 'Run probe',
      icon: rootProbeBusy ? 'bi-arrow-repeat sed-spin' : 'bi-broadcast-pin',
      variant: 'probe',
      disabled: actionsDisabled || rootProbeBusy,
      onClick: onRunRootProbe
    },
    {
      key: 'access-request',
      label: 'New access request',
      icon: 'bi-plus-lg',
      variant: 'primary',
      disabled: actionsDisabled,
      onClick: onNewAccessRequest
    },
    {
      key: 'edit',
      label: 'Edit storage root',
      icon: 'bi-pencil-square',
      variant: 'secondary',
      overflow: true,
      disabled: actionsDisabled,
      onClick: onEditRoot
    },
    {
      key: 'delete',
      label: 'Delete storage root',
      icon: 'bi-trash',
      variant: 'danger',
      overflow: true,
      disabled: actionsDisabled,
      onClick: onDeleteRoot
    }
  ] satisfies EntityActionItem[];
</script>

<EntityConsoleHeader
  eyebrow=""
  {title}
  statusLabel={showStatusBadge ? statusLabel : ''}
  statusTone={showStatusBadge ? resolvedStatusTone : 'neutral'}
  {metaItems}
  {actions}
  actionsAriaLabel="Storage root actions"
/>
