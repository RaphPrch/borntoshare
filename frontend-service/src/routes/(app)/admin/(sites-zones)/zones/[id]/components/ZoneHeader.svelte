<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityHeader from "$lib/components/entity/EntityHeader.svelte";
  import {
    type OperationalHeaderMetaItem
  } from "$lib/components/entity/EntityHeader.svelte";
  import { type EntityActionItem } from "$lib/components/entity/EntityActionGroup.svelte";
  import { healthLabelToOperationalTone } from "$lib/mappers/entity-operational.mapper";

  export let zone: any;
  export let endpointCount = 0;
  export let healthLabel: "ok" | "warning" = "warning";
  export let attentionItems: string[] = [];
  export let attentionMeta: string | null = null;
  export let showAttention = false;
  export let onEdit: (() => void) | null = null;
  export let onDelete: (() => void) | null = null;
  export let onAddEndpoint: (() => void) | null = null;

  $: statusTone = healthLabelToOperationalTone(healthLabel);
  $: statusLabel = healthLabel === "ok" ? t('All endpoints reachable') : t('Needs attention');
  $: zoneMetaItems = [
    { label: String(zone?.code ?? "-"), mono: true },
    { icon: "bi-hdd-network", label: endpointCount === 1 ? t('1 endpoint') : t('{count} endpoints', { count: endpointCount }) }
  ] satisfies OperationalHeaderMetaItem[];
  $: actions = [
    { key: "edit", label: t('Edit'), icon: "bi-pencil", variant: "secondary", onClick: () => onEdit?.() },
    ...(onAddEndpoint
      ? [{ key: "add-endpoint", label: t('Add endpoint'), icon: "bi-plus-lg", variant: "primary" as const, onClick: () => onAddEndpoint?.() }]
      : []),
    { key: "delete", label: t('Delete zone'), icon: "bi-trash", variant: "danger", overflow: true, onClick: () => onDelete?.() }
  ] satisfies EntityActionItem[];
</script>

<EntityHeader
  iconClass="bi-geo-alt"
  eyebrow={t('Zone')}
  title={zone?.name ?? t('Zone')}
  metaItems={zoneMetaItems}
  {statusTone}
  {statusLabel}
  {showAttention}
  attentionTitle={t('Attention required')}
  {attentionItems}
  attentionMeta={attentionMeta}
  containerClass="zone-console__operational-header"
  {actions}
  actionsAriaLabel={t('Zone actions')}
/>
