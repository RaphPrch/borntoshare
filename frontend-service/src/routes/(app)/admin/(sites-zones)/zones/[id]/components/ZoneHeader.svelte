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

  $: statusTone = healthLabelToOperationalTone(healthLabel);
  $: statusLabel = healthLabel === "ok" ? "Health OK" : "Health Warning";
  $: zoneMetaItems = [
    { icon: "bi-hash", label: String(zone?.code ?? "-") },
    { icon: "bi-hdd-network", label: t('{endpointCount} endpoint{value}', { endpointCount, value: (endpointCount > 1 ? "s" : "") }) }
  ] satisfies OperationalHeaderMetaItem[];
  $: actions = [
    {
      key: "edit",
      label: "Edit zone",
      icon: "bi-pencil-square",
      variant: "secondary",
      onClick: () => onEdit?.()
    },
    {
      key: "delete",
      label: "Delete zone",
      icon: "bi-trash",
      variant: "danger",
      onClick: () => onDelete?.()
    }
  ] satisfies EntityActionItem[];
</script>

<EntityHeader
  eyebrow=""
  title={t('{value} Console', { value: (zone?.name ?? t('Zone')) })}
  subtitle={String(zone?.site_name ?? "")}
  metaItems={zoneMetaItems}
  {statusTone}
  statusLabel=""
  statusIconClass=""
  {showAttention}
  attentionTitle={t('Attention required')}
  {attentionItems}
  attentionMeta={attentionMeta}
  containerClass="zone-console__operational-header"
  {actions}
  actionsAriaLabel={t('Zone actions')}
/>
