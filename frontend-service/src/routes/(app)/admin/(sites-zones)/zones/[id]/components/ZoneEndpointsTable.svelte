<script lang="ts">
  import { t } from '$lib/i18n';
  import DataTable from "$lib/components/ui/DataTable.svelte";
  import StatusBadge from "$lib/components/ui/StatusBadge.svelte";
  import type { StatusVariant } from "$lib/utils/status";
  import EntityActionButton from "$lib/components/entity/EntityActionButton.svelte";
  import {
    endpointOperationalStateLabel,
    endpointOperationalStateVariant,
    normalizeProbeStatus,
    probeStatusLabel,
    probeStatusVariant
  } from "$lib/mappers/entity-status.mapper";

  export let endpoints: any[] = [];
  export let probeResultsByEndpoint: Record<string, string> = {};
  export let onRunProbe: ((endpoint: any) => void) | null = null;

  const endpointId = (ep: any) => Number(ep?.id ?? ep?.storage_endpoint_id ?? 0);
  const lastProbeResult = (ep: any) => {
    const id = endpointId(ep);
    const runtime = id > 0 ? probeResultsByEndpoint[String(id)] : null;
    return runtime ?? String(ep?.last_probe_status ?? ep?.probe_status ?? "unknown");
  };

  const persistedOperationalState = (ep: any): string =>
    String(ep?.operational_state ?? '').trim().toLowerCase() || 'unknown';

  const endpointOperationalState = (ep: any): string => {
    const runtime = normalizeProbeStatus(lastProbeResult(ep));
    if (runtime === 'running') return 'checking';
    return persistedOperationalState(ep);
  };

  const probeRunning = (value: string): boolean => normalizeProbeStatus(value) === "running";
</script>

<DataTable
  columns={[
    { key: "name", label: t('Name') },
    { key: "address", label: t('Address') },
    { key: "status", label: t('Status'), sortable: true },
    { key: "last_probe", label: t('Last probe') },
    { key: "actions", label: "", className: "zone-endpoints__actions-col" },
  ]}
  rows={endpoints.map((ep) => ({
    endpoint_raw: ep,
    id: ep.id ?? ep.storage_endpoint_id ?? ep.name,
    name: ep.name ?? ep.storage_endpoint_name ?? t('Endpoint #{value}', { value: (ep.id ?? "-") }),
    address: ep.host ?? "-",
    last_probe: lastProbeResult(ep),
    probe_running: probeRunning(lastProbeResult(ep)),
    status_label: endpointOperationalStateLabel(endpointOperationalState(ep)),
    status_variant: endpointOperationalStateVariant(endpointOperationalState(ep)),
  }))}
>
  <svelte:fragment slot="cell" let:row let:column>
    {#if column.key === "name"}
      <span>{String(row?.name ?? "-")}</span>
    {:else if column.key === "status"}
      <StatusBadge
        status={String(row.status_label ?? t('Unknown'))}
        label={String(row.status_label ?? t('Unknown'))}
        variant={(row.status_variant ?? "muted") as StatusVariant}
        showDot={false}
      />
    {:else if column.key === "last_probe"}
      <StatusBadge
        status={String(row.last_probe ?? "unknown")}
        label={probeStatusLabel(String(row.last_probe ?? "unknown"))}
        variant={probeStatusVariant(String(row.last_probe ?? "unknown"))}
        showDot={false}
      />
    {:else if column.key === "actions"}
      <EntityActionButton
        iconOnly={true}
        variant="probe"
        icon="bi-activity"
        busyIcon="bi-hourglass-split"
        busy={Boolean(row.probe_running)}
        label={row.probe_running ? t('Probe in progress') : t('Run probe')}
        title={row.probe_running ? t('Probe in progress') : t('Run probe')}
        ariaLabel={row.probe_running ? t('Probe in progress') : t('Run probe for {String}', { String: String(row?.name ?? "endpoint") })}
        disabled={Boolean(row.probe_running)}
        stopPropagation={true}
        onClick={() => onRunProbe?.(row.endpoint_raw)}
      />
    {:else}
      {String(row?.[column.key] ?? "-")}
    {/if}
  </svelte:fragment>
</DataTable>

<style>
  :global(.zone-endpoints__actions-col) {
    width: 1%;
    text-align: right;
    white-space: nowrap;
  }
</style>
