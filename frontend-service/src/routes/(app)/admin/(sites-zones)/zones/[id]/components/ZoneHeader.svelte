<script lang="ts">
  import EntityConsoleHeader from "$lib/components/common/EntityConsoleHeader.svelte";
  import {
    type OperationalHeaderMetaItem
  } from "$lib/components/common/EntityOperationalHeader.svelte";
  import { type EntityActionItem } from "$lib/components/common/EntityActionGroup.svelte";
  import { healthLabelToOperationalTone } from "$lib/services/mappers/entity-operational.mapper";

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
    { icon: "bi-hdd-network", label: `${endpointCount} endpoint${endpointCount > 1 ? "s" : ""}` }
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

<EntityConsoleHeader
  eyebrow=""
  title={`${zone?.name ?? "Zone"} Console`}
  subtitle={String(zone?.site_name ?? "")}
  metaItems={zoneMetaItems}
  {statusTone}
  statusLabel=""
  statusIconClass=""
  {showAttention}
  attentionTitle="Attention required"
  {attentionItems}
  attentionMeta={attentionMeta}
  containerClass="zone-console__operational-header"
  {actions}
  actionsAriaLabel="Zone actions"
/>
