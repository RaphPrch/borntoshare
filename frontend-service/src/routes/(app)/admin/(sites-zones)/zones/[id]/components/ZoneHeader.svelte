<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityPageHeader from "$lib/components/entity/EntityPageHeader.svelte";
  import { type EntityActionItem } from "$lib/components/entity/EntityActionGroup.svelte";

  export let zone: any;
  export let endpointCount = 0;
  export let healthLabel: "ok" | "warning" = "warning";
  export let onEdit: (() => void) | null = null;
  export let onDelete: (() => void) | null = null;
  export let onAddEndpoint: (() => void) | null = null;

  // Nothing to report without a file server
  $: statusLabel = endpointCount === 0 ? "" : healthLabel === "ok" ? t('All endpoints reachable') : t('Needs attention');
  $: actions = [
    { key: "edit", label: t('Edit'), icon: "bi-pencil", variant: "secondary", onClick: () => onEdit?.() },
    ...(onAddEndpoint
      ? [{ key: "add-endpoint", label: t('Add endpoint'), icon: "bi-plus-lg", variant: "primary" as const, onClick: () => onAddEndpoint?.() }]
      : []),
    { key: "delete", label: t('Delete zone'), icon: "bi-trash", variant: "danger", overflow: true, onClick: () => onDelete?.() }
  ] satisfies EntityActionItem[];
</script>

<EntityPageHeader
  crumbs={[t('Zones')]}
  title={zone?.name ?? t('Zone')}
  {statusLabel}
  statusTone={healthLabel === "ok" ? "success" : "warning"}
  code={String(zone?.code ?? "")}
  {actions}
  actionsAriaLabel={t('Zone actions')}
/>
