<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityHeroCard from '$lib/components/entity/EntityHeroCard.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

  
  interface Props {
    /** Header of a zone, as a card: icon, name, one status pill, its code, directories and servers, actions. */
    zone: any;
    healthLabel?: 'ok' | 'warning';
    endpointCount?: number;
    directories?: string[];
    serversLabel?: string;
    onEdit?: (() => void) | null;
    onDelete?: (() => void) | null;
    onAddEndpoint?: (() => void) | null;
  }

  let {
    zone,
    healthLabel = 'warning',
    endpointCount = 0,
    directories = [],
    serversLabel = '',
    onEdit = null,
    onDelete = null,
    onAddEndpoint = null
  }: Props = $props();

  // Nothing to report without a server
  let statusLabel = $derived(endpointCount === 0 ? '' : healthLabel === 'ok' ? t('Under control') : t('Needs attention'));
  let actions = $derived([
    { key: 'edit', label: t('Edit'), icon: 'bi-pencil', variant: 'secondary', onClick: () => onEdit?.() },
    ...(onAddEndpoint
      ? [{ key: 'add-endpoint', label: t('Add a server'), icon: 'bi-plus-lg', variant: 'primary' as const, onClick: () => onAddEndpoint?.() }]
      : []),
    { key: 'delete', label: t('Delete zone'), icon: 'bi-trash', variant: 'danger', overflow: true, onClick: () => onDelete?.() }
  ] satisfies EntityActionItem[]);
</script>

<EntityHeroCard
  icon="bi-geo-alt"
  iconTone="blue"
  crumbs={[t('Zones')]}
  title={zone?.name ?? t('Zone')}
  {statusLabel}
  statusTone={healthLabel === 'ok' ? 'success' : 'warning'}
  chips={[
    ...(zone?.code ? [{ label: String(zone.code), mono: true }] : []),
    ...directories.map((directory) => ({ label: directory, icon: 'bi-diagram-3' })),
    ...(serversLabel ? [{ label: serversLabel, icon: 'bi-hdd-network' }] : [])
  ]}
  {actions}
  actionsAriaLabel={t('Zone actions')}
/>
