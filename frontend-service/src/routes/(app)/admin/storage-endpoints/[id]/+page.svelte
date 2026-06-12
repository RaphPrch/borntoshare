<script lang="ts">
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { goto, invalidateAll } from '$app/navigation';
  import EntityAlertDrawer from '$lib/components/common/EntityAlertDrawer.svelte';
  import EntityAlertStrip from '$lib/components/common/EntityAlertStrip.svelte';
  import type { EntityAlertStripItem } from '$lib/components/common/entity-alerts.types';
  import EntityTabs from '$lib/components/common/EntityTabs.svelte';
  import ConfirmActionModal from '$lib/components/common/ConfirmActionModal.svelte';
  import EmptyStateCard from '$lib/components/common/EmptyStateCard.svelte';
  import StorageEndpointsSidebar from '$lib/components/storage-endpoints/StorageEndpointsSidebar.svelte';
  import StorageEndpointWizardModal from '$lib/components/storage-endpoints/StorageEndpointWizardModal.svelte';
  import StorageEndpointEditModal from '$lib/components/storage-endpoints/StorageEndpointEditModal.svelte';
  import ProvisioningPolicyScreen from '$lib/components/provisioning/ProvisioningPolicyScreen.svelte';
  import {
    buildStorageEndpointProvisioningViewModel,
    type ProvisioningPolicyViewModel
  } from '$lib/components/provisioning/provisioning-policy.adapter';
  import EntityConsoleHeader from '$lib/components/common/EntityConsoleHeader.svelte';
  import {
    type OperationalHeaderMetaItem
  } from '$lib/components/common/EntityOperationalHeader.svelte';
  import { type EntityActionItem } from '$lib/components/common/EntityActionGroup.svelte';
  import RecentActivityCard from '$lib/components/activity/RecentActivityCard.svelte';
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';
  import EntityKpiRow from '$lib/components/common/EntityKpiRow.svelte';
  import EntityOverviewLayout from '$lib/components/common/EntityOverviewLayout.svelte';
  import AssociatedRootsTable from '$lib/components/storage-endpoints/detail/AssociatedRootsTable.svelte';
  import ActivityDetailsDrawer from '$lib/components/activity/ActivityDetailsDrawer.svelte';
  import EntityOverviewPanel from '$lib/components/common/EntityOverviewPanel.svelte';
  import EntityConsoleShell from '$lib/components/common/EntityConsoleShell.svelte';

  import {
    deleteStorageEndpoint,
    getStorageEndpointProvisioningPolicy,
    putStorageEndpointProvisioningPolicy,
    recordStorageEndpointProbeResult,
    updateStorageEndpoint,
    type StorageEndpointProvisioningPolicy,
    type StorageEndpointProvisioningUpdatePayload
  } from '$lib/api/storage-endpoints';
  import {
    buildProvisioningUpdatePayload,
    createProvisioningDraft
  } from '$lib/services/mappers/storage-endpoint-provisioning.mapper';
  import {
    mapBusinessOverallToVariant,
    normalizeProbeStatus,
    reachabilityFromProbeStatus
  } from '$lib/services/mappers/visual-state.mapper';
  import {
    endpointOperationalStateLabel,
    endpointOperationalStateStatus
  } from '$lib/services/mappers/endpoint-operational-state.mapper';
  import {
    buildStorageEndpointOperationalAttentionItems,
    endpointHealthToOperationalTone
  } from '$lib/services/mappers/entity-operational.mapper';
  import type { GovernanceAlert } from '$lib/api/governance-alerts';
  import {
    selectVisibleStorageRootAlertsForRootIds,
    storageRootAlertRootId,
    storageRootAlertSummarySubtitle,
    storageRootAlertTone
  } from '$lib/services/mappers/storage-root-alerts.mapper';
  import {
    collectStorageRootsAvailabilityByEndpoint,
    syncStorageRootDiscoveryForEndpoint,
    type StorageRootAvailabilitySummary
  } from '$lib/probe/probe-runner';
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from '$lib/probe/storage-endpoint-probe';
  import { runProbeWithPolling } from '$lib/probe/probe-runner';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError, logInfo, logWarning } from '$lib/core/logging';
  import { toast } from '$lib/utils/toast';
  import {
    dependencyCountDeleteMessage,
    dependencyDeleteMessage,
    isDependencyDeleteError
  } from '$lib/utils/delete-guard';

  const PROBE_SYNC_EVENT = 'b2s:storage-endpoint-probe-updated';

  export let data: {
    endpoints: any[];
    roots: any[];
    storageRootAlerts?: GovernanceAlert[];
    activity?: any[];
    pendingRequests?: any[];
  };

  let endpoints: any[] = Array.isArray(data.endpoints) ? data.endpoints : [];
  let roots: any[] = Array.isArray(data.roots) ? data.roots : [];
  let activity: any[] = Array.isArray(data.activity) ? data.activity : [];
  let pendingRequests: any[] = Array.isArray(data.pendingRequests) ? data.pendingRequests : [];

  $: endpoints = Array.isArray(data.endpoints) ? data.endpoints : [];
  $: roots = Array.isArray(data.roots) ? data.roots : [];
  $: activity = Array.isArray(data.activity) ? data.activity : [];
  $: pendingRequests = Array.isArray(data.pendingRequests) ? data.pendingRequests : [];

  const norm = (v?: string | null) => (v ?? '').toLowerCase().trim();
  const endpointId = (ep: any) => Number(ep?.id ?? ep?.storage_endpoint_id ?? 0);
  const endpointName = (ep: any) => String(ep?.name ?? ep?.storage_endpoint_name ?? 'Unavailable');
  const endpointProtocol = (ep: any) => String(ep?.protocol ?? ep?.type ?? ep?.storage_endpoint_type ?? '').toLowerCase();
  const endpointHost = (ep: any) => String(ep?.host ?? 'Unavailable');
  const endpointHasHost = (ep: any): boolean => {
    const host = String(ep?.host ?? '').trim();
    return Boolean(host) && host.toLowerCase() !== 'unavailable';
  };
  const endpointZone = (ep: any) => String(ep?.zone?.name ?? ep?.zone_name ?? 'Unavailable');
  const rootId = (row: any) => Number(row?.id ?? row?.storage_root_id ?? 0);
  const rootName = (row: any) => String(row?.name ?? row?.storage_root_name ?? 'Unavailable');
  const rootPath = (row: any) => String(row?.root_path ?? row?.path ?? row?.location ?? 'Unavailable');
  const rootsForEndpoint = (ep: any): any[] =>
    roots.filter((row) => Number(row?.storage_endpoint_id ?? 0) === endpointId(ep));

  const persistedOperationalState = (ep: any): string =>
    String(ep?.operational_state ?? '').trim().toLowerCase() || 'unknown';

  const endpointOperationalState = (ep: any): string =>
    probingEndpointId === endpointId(ep) ? 'checking' : persistedOperationalState(ep);

  const endpointTone = (ep: any): 'healthy' | 'warning' | 'error' => {
    const health = endpointHealth(ep);
    if (health === 'healthy') return 'healthy';
    if (health === 'degraded' || health === 'unknown') return 'warning';
    return 'error';
  };

  type HealthValue = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  let endpointHealthById: Record<string, HealthValue> = {};
  let rootHealthByEndpointId: Record<string, Record<string, HealthValue>> = {};
  let rootAvailabilityRowsByEndpointId: Record<string, StorageRootAvailabilitySummary['rows']> = {};
  let healthLoadingByEndpointId: Record<string, string> = {};
  let manualHealthRefreshByEndpointId: Record<string, boolean> = {};
  let probingEndpointId: number | null = null;
  let healthLoadedForEndpointId: number | null = null;

  function statusToHealth(status: string): HealthValue {
    const normalized = String(status ?? '').toLowerCase().trim();
    if (normalized === 'disabled' || normalized === 'inactive') return 'unhealthy';
    if (normalized === 'reachable' || normalized === 'success') return 'healthy';
    if (normalized === 'checking' || normalized === 'running') return 'degraded';
    if (normalized === 'unreachable' || normalized === 'failed') return 'unhealthy';
    const reachability = reachabilityFromProbeStatus(normalizeProbeStatus(status));
    if (reachability === 'reachable') return 'healthy';
    if (reachability === 'checking') return 'degraded';
    if (reachability === 'unreachable') return 'unhealthy';
    return 'unknown';
  }

  function endpointProbeOk(ep: any): boolean | undefined {
    const status = String(ep?.last_probe_status ?? ep?.probe_status ?? '').trim();
    if (!status) return undefined;
    const reachability = reachabilityFromProbeStatus(normalizeProbeStatus(status));
    if (reachability === 'reachable') return true;
    if (reachability === 'unreachable') return false;
    return undefined;
  }

  const endpointHealth = (ep: any): HealthValue => endpointHealthById[String(endpointId(ep))] ?? 'unknown';

  const rootHealth = (row: any): HealthValue => {
    const endpointKey = String(selectedId || 0);
    return rootHealthByEndpointId[endpointKey]?.[String(rootId(row))] ?? 'unknown';
  };

  const healthLabel = (value: HealthValue): string => {
    if (value === 'healthy') return 'Reachable';
    if (value === 'degraded') return 'Needs review';
    if (value === 'unhealthy') return 'Probe failed';
    return 'No probe yet';
  };

  const healthToneClass = (value: HealthValue): string => {
    if (value === 'healthy') return 'is-success';
    return 'is-danger';
  };

  const setHealthLoading = (endpointIdValue: number, stage: string | null) => {
    const key = String(endpointIdValue || 0);
    if (!key || key === '0') return;
    if (!stage) {
      const next = { ...healthLoadingByEndpointId };
      delete next[key];
      healthLoadingByEndpointId = next;
      return;
    }
    healthLoadingByEndpointId = {
      ...healthLoadingByEndpointId,
      [key]: stage
    };
  };

  const endpointHealthLoadingStage = (ep: any): string =>
    healthLoadingByEndpointId[String(endpointId(ep))] ?? '';

  const endpointHealthLoadingLabel = (ep: any): string => {
    const stage = endpointHealthLoadingStage(ep);
    if (stage === 'testing_endpoint') return 'Testing endpoint…';
    if (stage === 'syncing_roots') return 'Syncing roots…';
    return '';
  };

  const withTimeout = async <T,>(promise: Promise<T>, ms: number, message: string): Promise<T> => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    try {
      return await Promise.race([
        promise,
        new Promise<T>((_, reject) => {
          timeoutId = setTimeout(() => reject(new Error(message)), ms);
        })
      ]);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  };

  const setManualHealthRefresh = (endpointIdValue: number, busy: boolean): void => {
    const key = String(endpointIdValue || 0);
    if (!key || key === '0') return;
    if (!busy) {
      const next = { ...manualHealthRefreshByEndpointId };
      delete next[key];
      manualHealthRefreshByEndpointId = next;
      return;
    }
    manualHealthRefreshByEndpointId = {
      ...manualHealthRefreshByEndpointId,
      [key]: true
    };
  };

  const endpointManualHealthRefreshBusy = (ep: any): boolean =>
    Boolean(manualHealthRefreshByEndpointId[String(endpointId(ep))]);

  const formatDate = (value: unknown): string => {
    const text = String(value ?? '').trim();
    if (!text) return 'Unavailable';
    const date = new Date(text);
    if (!Number.isFinite(date.getTime())) return 'Unavailable';
    return date.toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatRelativeDate = (value: unknown, fallback = 'Unavailable'): string => {
    const text = String(value ?? '').trim();
    if (!text) return fallback;
    const date = new Date(text);
    if (!Number.isFinite(date.getTime())) return fallback;
    const diffMs = Date.now() - date.getTime();
    if (diffMs < 0) return formatDate(text);
    const seconds = Math.floor(diffMs / 1000);
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
    return formatDate(text);
  };

  function handleEndpointTabChange(key: string) {
    activeEndpointTab =
      key === 'provisioning'
        ? 'provisioning'
        : key === 'activity'
          ? 'activity'
          : 'overview';
  }

  $: hasEndpoints = endpoints.length > 0;
  $: selectedId = Number($page.params.id);
  $: selected = hasEndpoints
    ? endpoints.find((e) => Number(e?.id ?? e?.storage_endpoint_id) === selectedId) ?? null
    : null;

  $: if (browser && hasEndpoints && !selected) {
    goto(`/admin/storage-endpoints/${endpointId(endpoints[0])}`, { replaceState: true });
  }

  let openEditHandledFor: number | null = null;
  $: if (
    browser &&
    selected &&
    openEditHandledFor !== selectedId &&
    ['1', 'true'].includes(String($page.url.searchParams.get('openEdit') ?? '').toLowerCase())
  ) {
    openEditHandledFor = selectedId;
    showEditModal = true;
    const next = new URL($page.url);
    next.searchParams.delete('openEdit');
    goto(`${next.pathname}${next.search}`, { replaceState: true, noScroll: true });
  }

  let search = '';
  let openSidebarZones = new Set<string>();

  $: query = norm(search);
  $: sidebarEndpoints = endpoints.filter((ep) => {
    if (!query) return true;
    const target = [endpointName(ep), endpointZone(ep)]
      .map((v) => norm(v))
      .join(' ');
    return target.includes(query);
  });

  $: sidebarGroups = (() => {
    const map = new Map<string, { zone_id: string | number; zone_name: string; endpoints: any[] }>();
    for (const ep of sidebarEndpoints) {
      const zoneName = endpointZone(ep) || 'Unavailable';
      const rawZoneId = Number(ep?.zone_id ?? ep?.zone?.id ?? 0);
      const resolvedZoneId = Number.isFinite(rawZoneId) && rawZoneId > 0 ? rawZoneId : `unassigned-${endpointId(ep)}`;
      const key = String(resolvedZoneId);
      if (!map.has(key)) {
        map.set(key, {
          zone_id: resolvedZoneId,
          zone_name: zoneName,
          endpoints: []
        });
      }
      map.get(key)?.endpoints.push(ep);
    }
    return Array.from(map.values()).sort((a, b) =>
      a.zone_name.localeCompare(b.zone_name, 'en', { sensitivity: 'base' })
    );
  })();

  $: {
    let changed = false;
    const next = new Set(openSidebarZones);

    for (const zone of sidebarGroups) {
      const zoneKey = String(zone.zone_id);
      if (!next.has(zoneKey)) {
        next.add(zoneKey);
        changed = true;
      }
    }

    for (const zoneName of Array.from(next)) {
      if (!sidebarGroups.some((zone) => String(zone.zone_id) === zoneName)) {
        next.delete(zoneName);
        changed = true;
      }
    }

    if (changed) openSidebarZones = next;
  }

  const isSidebarZoneOpen = (zoneId: string | number): boolean => openSidebarZones.has(String(zoneId));

  const toggleSidebarZone = (zoneId: string | number): void => {
    const key = String(zoneId);
    const next = new Set(openSidebarZones);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    openSidebarZones = next;
  };

  const selectSidebarEndpoint = (id: number): void => {
    if (id > 0) goto(`/admin/storage-endpoints/${id}`);
  };

  $: selectedRoots = roots.filter((r) => Number(r?.storage_endpoint_id ?? 0) === selectedId);

  type EndpointTabKey = 'overview' | 'activity' | 'provisioning';
  const endpointTabs: { key: EndpointTabKey; label: string; icon: string }[] = [
    { key: 'overview', label: 'Overview', icon: 'bi-grid' },
    { key: 'activity', label: 'Activity', icon: 'bi-activity' },
    { key: 'provisioning', label: 'Provisioning', icon: 'bi-shield-check' }
  ];
  let activeEndpointTab: EndpointTabKey = 'overview';

  let endpointProvisioningBusy = false;
  let endpointProvisioningError: string | null = null;
  let endpointProvisioningPolicy: StorageEndpointProvisioningPolicy | null = null;
  let endpointProvisioningLoadedForId: number | null = null;

  let endpointProvisioningDraft: {
    policyMode: 'inherit' | 'override';
    ouDn: string;
    namingTemplate: string;
  } = {
    policyMode: 'inherit',
    ouDn: '',
    namingTemplate: ''
  };

  let lastSelectedEndpointIdForTabReset: number | null = null;
  $: if (selectedId > 0 && lastSelectedEndpointIdForTabReset !== selectedId) {
    activeEndpointTab = 'overview';
    lastSelectedEndpointIdForTabReset = selectedId;
  }

  const selectedEndpointId = () => endpointId(selected);

  function persistedEndpointHealth(endpointIdValue: number): HealthValue {
    const ep = endpoints.find((row) => endpointId(row) === endpointIdValue);
    if (!ep) return 'unknown';
    return statusToHealth(endpointOperationalState(ep));
  }

  function applyAvailabilityHealth(
    endpointIdValue: number,
    availability: StorageRootAvailabilitySummary,
    opts?: { probeOk?: boolean }
  ): void {
    const endpointKey = String(endpointIdValue);
    const mappedRootHealth: Record<string, HealthValue> = {};

    for (const row of availability.rows ?? []) {
      const rowRootId = Number(row?.storage_root_id ?? 0);
      if (rowRootId <= 0) continue;
      mappedRootHealth[String(rowRootId)] = row.available ? 'healthy' : 'unhealthy';
    }

    for (const row of roots ?? []) {
      const rowEndpointId = Number(row?.storage_endpoint_id ?? 0);
      if (rowEndpointId !== endpointIdValue) continue;
      const id = rootId(row);
      if (id <= 0) continue;
      if (!mappedRootHealth[String(id)]) mappedRootHealth[String(id)] = 'unknown';
    }

    rootHealthByEndpointId = {
      ...rootHealthByEndpointId,
      [endpointKey]: mappedRootHealth
    };
    rootAvailabilityRowsByEndpointId = {
      ...rootAvailabilityRowsByEndpointId,
      [endpointKey]: availability.rows ?? []
    };

    let endpointHealthValue: HealthValue = 'unknown';
    const probeKnown = typeof opts?.probeOk === 'boolean';
    const probeOk = opts?.probeOk === true;

    if (probeKnown && !probeOk) {
      endpointHealthValue = 'unhealthy';
    } else if (probeKnown && probeOk) {
      endpointHealthValue = 'healthy';
    } else if (availability.total > 0) {
      if (availability.unavailable <= 0) endpointHealthValue = 'healthy';
      else endpointHealthValue = availability.available <= 0 ? 'unhealthy' : 'degraded';
    } else {
      endpointHealthValue = persistedEndpointHealth(endpointIdValue);
    }

    endpointHealthById = {
      ...endpointHealthById,
      [endpointKey]: endpointHealthValue
    };
  }

  async function refreshEndpointHealth(ep: any, options?: { manual?: boolean }): Promise<void> {
    const id = endpointId(ep);
    if (!id) return;

    setHealthLoading(id, 'analyzing');
    if (options?.manual) setManualHealthRefresh(id, true);
    try {
      const availability = await withTimeout(
        collectStorageRootsAvailabilityByEndpoint(fetch, id),
        15000,
        'Endpoint status refresh timed out.'
      );
      applyAvailabilityHealth(id, availability, { probeOk: endpointProbeOk(ep) });
    } catch (err) {
      logWarning('Storage endpoint availability refresh failed', {
        endpointId: id,
        error: err instanceof Error ? err.message : String(err ?? 'unknown error')
      });
      endpointHealthById = {
        ...endpointHealthById,
        [String(id)]: persistedEndpointHealth(id)
      };
    } finally {
      setHealthLoading(id, null);
      if (options?.manual) setManualHealthRefresh(id, false);
    }
  }

  function refreshSelectedEndpointStatus(): void {
    if (!selected || selectedId <= 0) return;
    healthLoadedForEndpointId = selectedId;
    void refreshEndpointHealth(selected, { manual: true });
  }

  $: if (selected && selectedId > 0 && healthLoadedForEndpointId !== selectedId) {
    healthLoadedForEndpointId = selectedId;
    void refreshEndpointHealth(selected);
  }

  $: if (
    selectedEndpointId() > 0 &&
    activeEndpointTab === 'provisioning' &&
    !endpointProvisioningBusy &&
    endpointProvisioningLoadedForId !== selectedEndpointId()
  ) {
    void loadEndpointProvisioningPolicy(selectedEndpointId());
  }

  const resetEndpointProvisioningDraft = (policy: StorageEndpointProvisioningPolicy | null) => {
    endpointProvisioningDraft = createProvisioningDraft(policy);
  };

  $: endpointCurrentMode = endpointProvisioningPolicy?.policy_mode === 'override' ? 'override' : 'inherit';
  $: endpointCurrentOuDn = String(
    endpointCurrentMode === 'override'
      ? endpointProvisioningPolicy?.endpoint_values?.ou_dn
      : endpointProvisioningPolicy?.inherited_values?.ou_dn
  ).trim();
  $: endpointCurrentNamingTemplate = String(
    endpointCurrentMode === 'override'
      ? endpointProvisioningPolicy?.endpoint_values?.naming_template
      : endpointProvisioningPolicy?.inherited_values?.naming_template
  ).trim();

  $: endpointIsDirty =
    endpointProvisioningDraft.policyMode !== endpointCurrentMode ||
    String(endpointProvisioningDraft.ouDn ?? '').trim() !== endpointCurrentOuDn ||
    String(endpointProvisioningDraft.namingTemplate ?? '').trim() !== endpointCurrentNamingTemplate;

  $: endpointCanSave =
    Boolean(selected && selectedId && endpointProvisioningPolicy) &&
    !endpointProvisioningBusy &&
    endpointIsDirty;

  async function loadEndpointProvisioningPolicy(id: number) {
    try {
      const policy = await getStorageEndpointProvisioningPolicy(fetch, id);
      endpointProvisioningPolicy = policy;
      resetEndpointProvisioningDraft(policy);
      endpointProvisioningError = null;
      endpointProvisioningLoadedForId = id;
    } catch (e) {
      endpointProvisioningError = String((e as any)?.message ?? 'Unable to load endpoint provisioning policy.');
      endpointProvisioningLoadedForId = null;
    }
  }

  async function saveEndpointProvisioning() {
    if (!selected || !selectedId || !endpointCanSave) return;
    endpointProvisioningBusy = true;
    endpointProvisioningError = null;
    try {
      const payload: StorageEndpointProvisioningUpdatePayload = buildProvisioningUpdatePayload(
        endpointProvisioningDraft
      );

      const updated = await putStorageEndpointProvisioningPolicy(fetch, selectedId, payload);
      endpointProvisioningPolicy = updated;
      resetEndpointProvisioningDraft(updated);
      toast.success('Endpoint provisioning policy updated.');
      await invalidateAll();
    } catch (e) {
      endpointProvisioningError = String((e as any)?.message ?? 'Unable to save endpoint provisioning policy.');
      toast.error(endpointProvisioningError);
    } finally {
      endpointProvisioningBusy = false;
    }
  }

  async function persistEndpointProbeSnapshot(
    endpointIdValue: number,
    payload: {
      last_probe_status: string;
      last_probe_at: string;
      last_probe_message: string | null;
    }
  ): Promise<void> {
    if (!endpointIdValue) return;

    endpoints = endpoints.map((row) => {
      if (endpointId(row) !== endpointIdValue) return row;
      return {
        ...row,
        last_probe_status: payload.last_probe_status,
        last_probe_at: payload.last_probe_at,
        last_probe_message: payload.last_probe_message
      };
    });

    let persisted = true;
    try {
      await recordStorageEndpointProbeResult(fetch, endpointIdValue, {
        ...payload,
        source_type: 'storage_endpoint_ui_probe'
      });
    } catch (e) {
      persisted = false;
      logWarning('Storage endpoint probe snapshot persistence failed', {
        action: 'storage_endpoints.detail.probe.persist_failed',
        route: `/admin/storage-endpoints/${selectedId}`,
        endpointId: endpointIdValue,
        error: String((e as any)?.message ?? e ?? 'unknown')
      });
    }

    if (browser) {
      window.dispatchEvent(
        new CustomEvent(PROBE_SYNC_EVENT, {
          detail: {
            endpoint_id: endpointIdValue,
            last_probe_status: payload.last_probe_status,
            last_probe_at: payload.last_probe_at,
            last_probe_message: payload.last_probe_message,
            persisted
          }
        })
      );
    }
  }

  async function runEndpointProbe(ep: any) {
    if (!ep) return;

    const probeConfig = resolveStorageEndpointProbeConfig(ep);
    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Storage endpoint' });
    const id = probeConfig.endpointId;

    if (!validation.ok) {
      logWarning('Probe blocked: invalid endpoint config', {
        action: 'storage_endpoints.detail.probe.blocked.invalid_config',
        route: `/admin/storage-endpoints/${selectedId}`,
        endpointId: id,
        protocol: probeConfig.protocol,
        message: validation.message
      });
      toast.error(validation.message ?? 'Invalid endpoint probe configuration.');
      return;
    }

    probingEndpointId = id;
    setHealthLoading(id, 'testing_endpoint');
    endpoints = endpoints.map((row) =>
      endpointId(row) === id
        ? { ...row, last_probe_status: 'running' }
        : row
    );
    try {
      logInfo('Storage endpoint probe started', {
        action: 'storage_endpoints.detail.probe.started',
        route: `/admin/storage-endpoints/${selectedId}`,
        endpointId: id,
        protocol: probeConfig.protocol,
        host: probeConfig.host
      });

      const request = buildStorageEndpointProbeRequestFromEndpoint(ep, {
        discover: false,
        timeoutSec: 20,
        uiOrigin: 'admin'
      });

      const final = await runProbeWithPolling({
        fetchFn: fetch,
        request,
        intervalMs: 1500,
        maxAttempts: 40,
      });

      const probeAt = new Date().toISOString();

      if (final.ok) {
        await persistEndpointProbeSnapshot(id, {
          last_probe_status: 'success',
          last_probe_at: probeAt,
          last_probe_message: 'endpoint probe completed'
        });

        try {
          setHealthLoading(id, 'analyzing');
          const availability = await withTimeout(
            collectStorageRootsAvailabilityByEndpoint(fetch, id),
            15000,
            'Endpoint status refresh timed out after probe.'
          );
          applyAvailabilityHealth(id, availability, { probeOk: true });
        } catch (e) {
          logWarning('Storage endpoint availability refresh failed after successful probe', {
            action: 'storage_endpoints.detail.probe.refresh_failed',
            route: `/admin/storage-endpoints/${selectedId}`,
            endpointId: id,
            error: String((e as any)?.message ?? e ?? 'unknown')
          });
          if (selectedRoots.length === 0) {
            applyAvailabilityHealth(
              id,
              { total: 0, available: 0, unavailable: 0, rows: [] },
              { probeOk: true }
            );
          }
        }
        logInfo('Storage endpoint probe succeeded', {
          action: 'storage_endpoints.detail.probe.succeeded',
          route: `/admin/storage-endpoints/${selectedId}`,
          endpointId: id
        });
        toast.success(`Probe OK for ${endpointName(ep)}.`);
        await invalidateAll();
      } else {
        await persistEndpointProbeSnapshot(id, {
          last_probe_status: 'failed',
          last_probe_at: probeAt,
          last_probe_message: String(final.errorMessage ?? 'Probe failed')
        });

        applyAvailabilityHealth(
          id,
          { total: 0, available: 0, unavailable: 0, rows: [] },
          { probeOk: false }
        );
        toast.error(`Probe failed for ${endpointName(ep)}.`);
        await invalidateAll();
      }
    } catch (e) {
      const err = toAppError(e, { source: 'ui' });

      await persistEndpointProbeSnapshot(id, {
        last_probe_status: 'failed',
        last_probe_at: new Date().toISOString(),
        last_probe_message: String(err?.message ?? 'Probe failed')
      });

      applyAvailabilityHealth(
        id,
        { total: 0, available: 0, unavailable: 0, rows: [] },
        { probeOk: false }
      );
      logAppError(err, {
        action: 'storage_endpoints.detail.probe.failed',
        route: `/admin/storage-endpoints/${selectedId}`,
        endpointId: id
      });
      notifyError(err);
      await invalidateAll();
    } finally {
      probingEndpointId = null;
      setHealthLoading(id, null);
    }
  }

  let showWizard = false;
  let showEditModal = false;
  let showDeleteModal = false;
  let showEndpointAlertsDrawer = false;
  let endpointAlertItems: EntityAlertStripItem[] = [];
  let deleteBusy = false;
  let endpointToDelete: any | null = null;

  function openDeleteModal(ep: any) {
    if (!ep) return;
    const attachedRootCount = roots.filter((row) => Number(row?.storage_endpoint_id ?? 0) === endpointId(ep)).length;
    if (attachedRootCount > 0) {
      toast.error(dependencyCountDeleteMessage('storage endpoint', attachedRootCount, 'storage root'));
      return;
    }

    endpointToDelete = ep;
    showDeleteModal = true;
  }

  function closeDeleteModal() {
    showDeleteModal = false;
    deleteBusy = false;
    endpointToDelete = null;
  }

  async function removeEndpoint() {
    if (!endpointToDelete) return;

    deleteBusy = true;
    try {
      await deleteStorageEndpoint(fetch, endpointId(endpointToDelete));
      toast.success('Storage endpoint deleted.');
      closeDeleteModal();
      await goto('/admin/storage-endpoints');
    } catch (e) {
      if (isDependencyDeleteError(e)) {
        toast.error(dependencyDeleteMessage('storage endpoint', 'storage roots'));
        closeDeleteModal();
        return;
      }
      toast.error((e as any)?.message ?? 'Unable to delete endpoint.');
    } finally {
      deleteBusy = false;
    }
  }

  const pendingCountForRoot = (row: any): number | null => {
    const embedded = Number(row?.pending_validation_count);
    if (Number.isFinite(embedded)) return Math.max(0, embedded);
    return null;
  };

  const endpointPendingCount = (ep: any): number => {
    const embedded = Number(ep?.pending_requests_count);
    return Number.isFinite(embedded) && embedded > 0 ? embedded : 0;
  };

  const rootStatusLabel = (row: any): string => {
    const value = String(row?.status ?? row?.governance_status ?? '').trim();
    return value || 'No data';
  };

  const rootAvailabilityRow = (row: any): StorageRootAvailabilitySummary['rows'][number] | null =>
    (rootAvailabilityRowsByEndpointId[String(selectedId)] ?? []).find(
      (candidate) => Number(candidate?.storage_root_id ?? 0) === rootId(row)
    ) ?? null;

  const rootAvailabilityLabel = (row: any): string => {
    const health = rootHealth(row);
    if (health === 'healthy') return 'Ready';
    if (health === 'unhealthy') return 'Needs review';
    return 'No status';
  };

  const rootAvailabilityTone = (row: any): 'success' | 'warning' | 'danger' | 'muted' => {
    const health = rootHealth(row);
    if (health === 'healthy') return 'success';
    if (health === 'unhealthy') return 'danger';
    return 'muted';
  };

  const rootAvailabilityDetail = (row: any): string => {
    const availability = rootAvailabilityRow(row);
    if (!availability) return 'Run or refresh endpoint status to load details.';

    const provisioningStatus = String(availability.provisioning_status ?? '').trim();
    const endpointStatus = String(availability.endpoint_status ?? '').trim();

    if (availability.available) return 'Provisioning ready and endpoint probe succeeded.';
    if (provisioningStatus && !['ready', 'success'].includes(provisioningStatus.toLowerCase())) {
      return `Provisioning: ${provisioningStatus}`;
    }
    if (endpointStatus && normalizeProbeStatus(endpointStatus) !== 'success') {
      return `Probe: ${endpointStatus}`;
    }
    return 'Availability could not be confirmed.';
  };

  $: rootsFilteredRows = selectedRoots
    .map((row) => ({
      id: rootId(row),
      name: String(rootName(row) || '').replace(/^\s*\[[^\]]+\]\s*/, ''),
      path: rootPath(row),
      pendingCount: pendingCountForRoot(row)
    }));

  let activityDetailsOpen = false;
  let selectedActivityEntry: Record<string, unknown> | null = null;

  function openActivityDetails(entry: Record<string, unknown> | null) {
    selectedActivityEntry = entry ?? null;
    activityDetailsOpen = Boolean(selectedActivityEntry);
  }

  function closeActivityDetails() {
    activityDetailsOpen = false;
    selectedActivityEntry = null;
  }

  const endpointLastProbeRaw = (ep: any): string | null =>
    String(ep?.last_probe_at ?? ep?.updated_at ?? '').trim() || null;

  const endpointLastProbeLabel = (ep: any): string => {
    const raw = endpointLastProbeRaw(ep);
    return raw ? formatRelativeDate(raw, 'No probe data') : 'No probe data';
  };

  const endpointLastCommunicationLabel = (ep: any): string => {
    const raw = endpointLastProbeRaw(ep);
    return raw ? formatDate(raw) : 'No probe data';
  };

  const endpointLastResultLabel = (ep: any): string => {
    const message = String(ep?.last_probe_message ?? '').trim();
    if (message) return message;
    return endpointHealth(ep) === 'healthy' ? 'Reachable' : 'Unreachable';
  };

  const unavailableRootDetails = (endpointIdValue: number): string[] => {
    const rows = Object.entries(rootHealthByEndpointId[String(endpointIdValue)] ?? {})
      .filter(([, health]) => health !== 'healthy')
      .map(([id]) => {
        const row = selectedRoots.find((candidate) => rootId(candidate) === Number(id));
        return row ? rootName(row) : `Root #${id}`;
      });

    return rows.slice(0, 3);
  };

  const endpointHealthDetail = (ep: any): string | null => {
    const health = endpointHealth(ep);
    const lastResult = endpointLastResultLabel(ep);

    if (health === 'healthy') return null;
    if (health === 'unknown') return 'run a probe or refresh status to collect the latest result';
    if (health === 'unhealthy') return lastResult || 'last probe failed';

    const unavailableRoots = unavailableRootDetails(endpointId(ep));
    if (unavailableRoots.length > 0) {
      return `endpoint probe is reachable, but unavailable roots need review (${unavailableRoots.join(', ')})`;
    }

    return lastResult || 'probe or configuration needs review';
  };

  $: kpiItems = selected
    ? [
        {
          key: 'roots',
          label: 'Governed storage roots',
          value: String(selectedRoots.length),
          tone: 'info',
          icon: 'bi-diagram-3'
        },
        {
          key: 'pending',
          label: 'Pending requests',
          value: String(endpointPendingCount(selected)),
          hint: endpointPendingCount(selected) > 0 ? 'Requests awaiting review' : 'No pending requests',
          tone: endpointPendingCount(selected) > 0 ? 'warning' : 'neutral',
          icon: 'bi-inbox'
        }
      ]
    : [];

  $: provisioningWarnings = endpointProvisioningPolicy?.warnings?.map((w) => String(w?.message ?? '').trim()).filter(Boolean) ?? [];

  const endpointOperationalTone = (ep: any) => endpointHealthToOperationalTone(endpointHealth(ep));

  const endpointHeaderMetaItems = (ep: any): OperationalHeaderMetaItem[] => [
    { icon: 'bi-folder2-open', label: endpointZone(ep) },
    { icon: 'bi-diagram-3', label: `${selectedRoots.length} governed root${selectedRoots.length > 1 ? 's' : ''}` },
    {
      icon: 'bi-inbox',
      label: `${endpointPendingCount(ep)} pending request${endpointPendingCount(ep) > 1 ? 's' : ''}`,
      tone: endpointPendingCount(ep) > 0 ? 'warning' : 'neutral'
    },
    { icon: 'bi-hdd-network', label: endpointHasHost(ep) ? endpointHost(ep) : 'No host configured', tone: endpointHasHost(ep) ? 'neutral' : 'warning' },
    { icon: 'bi-clock-history', label: endpointLastProbeLabel(ep), tone: endpointHealth(ep) === 'healthy' ? 'success' : 'warning' }
  ];

  const endpointAttentionItems = (ep: any, options?: { includeProvisioningWarnings?: boolean }): string[] =>
    buildStorageEndpointOperationalAttentionItems({
      healthLabel: healthLabel(endpointHealth(ep)),
      healthDetail: endpointHealthDetail(ep),
      hostReady: endpointHasHost(ep),
      hostLabel: endpointHost(ep),
      pendingRequestCount: endpointPendingCount(ep),
      provisioningWarnings: options?.includeProvisioningWarnings ? provisioningWarnings : []
    });

  const endpointAlertToneFromText = (value: string): 'warning' | 'error' => {
    const text = String(value ?? '').toLowerCase();
    return text.includes('unreachable') || text.includes('failed') || text.includes('missing host')
      ? 'error'
      : 'warning';
  };

  const operationalAlertItemsForEndpoint = (ep: any, options?: { includeProvisioningWarnings?: boolean }): EntityAlertStripItem[] =>
    endpointAttentionItems(ep, options).map((item, index) => ({
      key: `endpoint-operational-alert-${endpointId(ep)}-${index}-${item}`,
      title: item,
      subtitle: index === 0 ? `Last probe: ${endpointLastCommunicationLabel(ep)}` : null,
      tone: endpointAlertToneFromText(item)
    }));

  const rootGovernanceAlertItemsForEndpoint = (ep: any): EntityAlertStripItem[] => {
    const endpointRoots = rootsForEndpoint(ep);
    const rootIds = endpointRoots.map((row) => rootId(row));
    const rootLabels = new Map(endpointRoots.map((row) => [rootId(row), rootName(row)]));
    return selectVisibleStorageRootAlertsForRootIds(rootIds, data.storageRootAlerts ?? []).map((alert) => {
      const alertRootId = storageRootAlertRootId(alert);
      const rootLabel = rootLabels.get(alertRootId) ?? `Storage root #${alertRootId}`;
      const detail = storageRootAlertSummarySubtitle(alert);
      return {
        key: `endpoint-root-alert-${endpointId(ep)}-${String(alert?.alert_key ?? alert?.id ?? `${alert?.alert_type ?? 'alert'}-${alertRootId}`)}`,
        title: String(alert?.title ?? 'Attention required'),
        subtitle: detail ? `${rootLabel} · ${detail}` : rootLabel,
        tone: storageRootAlertTone(alert)
      };
    });
  };

  const dedupeAlertItems = (items: EntityAlertStripItem[]): EntityAlertStripItem[] => {
    const seen = new Set<string>();
    const out: EntityAlertStripItem[] = [];
    for (const item of items) {
      const key = `${String(item.title ?? '').trim().toLowerCase()}|${String(item.subtitle ?? '').trim().toLowerCase()}`;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  };

  const buildStorageEndpointAlerts = (ep: any, options?: { includeProvisioningWarnings?: boolean }): EntityAlertStripItem[] =>
    dedupeAlertItems([
      ...operationalAlertItemsForEndpoint(ep, options),
      ...rootGovernanceAlertItemsForEndpoint(ep)
    ]);

  const endpointAlertCount = (ep: any): number => buildStorageEndpointAlerts(ep).length;

  const endpointAlertIndicator = (ep: any): { kind: 'warning' | 'error'; label: string } | null => {
    const items = buildStorageEndpointAlerts(ep);
    if (items.length <= 0) return null;
    return {
      kind: items.some((item) => item.tone === 'error') ? 'error' : 'warning',
      label: `${items.length} alert${items.length > 1 ? 's' : ''}`
    };
  };

  $: endpointAlertItems = selected
    ? buildStorageEndpointAlerts(selected, { includeProvisioningWarnings: true })
    : [];

  const endpointHeaderActions = (ep: any): EntityActionItem[] => [
    {
      key: 'probe',
      label: probingEndpointId === endpointId(ep) ? 'Probe running...' : 'Run probe',
      icon: probingEndpointId === endpointId(ep) ? 'bi-arrow-repeat sed-spin' : 'bi-broadcast-pin',
      variant: 'probe',
      disabled: probingEndpointId === endpointId(ep),
      onClick: () => runEndpointProbe(ep)
    },
    {
      key: 'refresh-status',
      label: endpointManualHealthRefreshBusy(ep) ? 'Refreshing...' : 'Refresh status',
      icon: endpointManualHealthRefreshBusy(ep) ? 'bi-arrow-repeat sed-spin' : 'bi-arrow-clockwise',
      variant: 'secondary',
      disabled: endpointManualHealthRefreshBusy(ep),
      onClick: refreshSelectedEndpointStatus
    },
    {
      key: 'edit',
      label: 'Edit storage endpoint',
      icon: 'bi-pencil-square',
      variant: 'secondary',
      onClick: () => (showEditModal = true)
    },
    {
      key: 'delete',
      label: 'Delete storage endpoint',
      icon: 'bi-trash',
      variant: 'danger',
      onClick: () => openDeleteModal(ep)
    }
  ];

  let endpointProvisioningViewModel: ProvisioningPolicyViewModel =
    buildStorageEndpointProvisioningViewModel(null);

  const previewGroupName = (templateRaw: unknown, permRaw: 'RX' | 'RW'): string | null => {
    const policy = (endpointProvisioningPolicy as any)?.effective_naming_policy ?? {};
    const template = String(templateRaw ?? '').trim() || '{PREFIX}_{ROOTCODE}_{PERM}';
    const prefix = String(policy?.group_prefix ?? 'B2S').trim() || 'B2S';
    const uppercase = policy?.normalize_uppercase !== false;
    const rootCode = uppercase ? 'FINANCE_RW' : 'finance_rw';
    const rendered = template
      .replaceAll('{PREFIX}', prefix)
      .replaceAll('{ROOTCODE}', rootCode)
      .replaceAll('{PERM}', permRaw);
    return uppercase ? rendered.toUpperCase() : rendered;
  };

  $: {
    const policy = endpointProvisioningPolicy;
    const draft = endpointProvisioningDraft;

    const computedPolicy = policy
      ? {
          ...policy,
          policy_mode: draft.policyMode,
          policy_source: draft.policyMode === 'override' ? 'endpoint' : policy.policy_source,
          policy_source_label:
            draft.policyMode === 'override' ? 'Endpoint override' : policy.policy_source_label,
          endpoint_values: {
            ...(policy.endpoint_values ?? { ou_dn: null, naming_template: null }),
            ou_dn: draft.policyMode === 'override' ? draft.ouDn : null,
            naming_template: draft.policyMode === 'override' ? draft.namingTemplate : null
          },
          effective_values:
            draft.policyMode === 'override'
              ? {
                  ...(policy.effective_values ?? { ou_dn: null, naming_template: null }),
                  ou_dn:
                    String(draft.ouDn ?? '').trim() ||
                    policy.inherited_values?.ou_dn ||
                    policy.effective_values?.ou_dn ||
                    null,
                  naming_template:
                    String(draft.namingTemplate ?? '').trim() ||
                    policy.inherited_values?.naming_template ||
                    policy.effective_values?.naming_template ||
                    null
                }
              : {
                  ...(policy.effective_values ?? { ou_dn: null, naming_template: null }),
                  ou_dn: policy.inherited_values?.ou_dn ?? policy.effective_values?.ou_dn ?? null,
                  naming_template:
                    policy.inherited_values?.naming_template ??
                    policy.effective_values?.naming_template ??
                    null
                }
              ,
          effective_naming_policy: {
            ...((policy as any).effective_naming_policy ?? {}),
            template:
              draft.policyMode === 'override'
                ? String(draft.namingTemplate ?? '').trim() ||
                  policy.inherited_values?.naming_template ||
                  policy.effective_values?.naming_template ||
                  (policy as any).effective_naming_policy?.template ||
                  null
                : policy.inherited_values?.naming_template ??
                  policy.effective_values?.naming_template ??
                  (policy as any).effective_naming_policy?.template ??
                  null
          },
          example_groups:
            draft.policyMode === 'override'
              ? {
                  ...(policy.example_groups ?? {}),
                  read: previewGroupName(
                    String(draft.namingTemplate ?? '').trim() ||
                      policy.inherited_values?.naming_template ||
                      policy.effective_values?.naming_template ||
                      (policy as any).effective_naming_policy?.template,
                    'RX'
                  ),
                  write: previewGroupName(
                    String(draft.namingTemplate ?? '').trim() ||
                      policy.inherited_values?.naming_template ||
                      policy.effective_values?.naming_template ||
                      (policy as any).effective_naming_policy?.template,
                    'RW'
                  )
                }
              : policy.example_groups
        }
      : null;

    const base = buildStorageEndpointProvisioningViewModel(computedPolicy);
    endpointProvisioningViewModel = {
      ...base,
      configuration: {
        ...base.configuration,
        inheritanceMode: draft.policyMode,
        inheritanceModeLocked: false,
        onChangeInheritanceMode: (next) => {
          const mode = next === 'override' ? 'override' : 'inherit';
          endpointProvisioningDraft = {
            ...endpointProvisioningDraft,
            policyMode: mode,
            ouDn:
              mode === 'override'
                ? String(endpointProvisioningDraft.ouDn ?? '')
                : String(endpointProvisioningPolicy?.inherited_values?.ou_dn ?? ''),
            namingTemplate:
              mode === 'override'
                ? String(endpointProvisioningDraft.namingTemplate ?? '')
                : String(endpointProvisioningPolicy?.inherited_values?.naming_template ?? '')
          };
        },
        onChangeOrganizationalUnit: (value) => {
          endpointProvisioningDraft = {
            ...endpointProvisioningDraft,
            ouDn:
              endpointProvisioningDraft.policyMode === 'override'
                ? String(value ?? '')
                : String(endpointProvisioningPolicy?.inherited_values?.ou_dn ?? '')
          };
        },
        onChangeNamingTemplate: (value) => {
          endpointProvisioningDraft = {
            ...endpointProvisioningDraft,
            namingTemplate:
              endpointProvisioningDraft.policyMode === 'override'
                ? String(value ?? '')
                : String(endpointProvisioningPolicy?.inherited_values?.naming_template ?? '')
          };
        },
        onUseZoneValues: () => {
          endpointProvisioningDraft = {
            ...endpointProvisioningDraft,
            policyMode: 'inherit',
            ouDn: String(endpointProvisioningPolicy?.inherited_values?.ou_dn ?? ''),
            namingTemplate: String(endpointProvisioningPolicy?.inherited_values?.naming_template ?? '')
          };
        }
      }
    };
  }
</script>

<div class="sed-layout" class:sed-layout--empty={!hasEndpoints}>
  {#if hasEndpoints}
    <StorageEndpointsSidebar
      query={search}
      groups={sidebarGroups}
      selectedEndpointId={selectedId}
      isOpenZone={isSidebarZoneOpen}
      onToggleZone={toggleSidebarZone}
      onSelectEndpoint={selectSidebarEndpoint}
      onCreateEndpoint={() => (showWizard = true)}
      onQueryChange={(value) => (search = value)}
      showToneDot={false}
      {endpointId}
      {endpointName}
      {endpointTone}
      {endpointAlertCount}
      {endpointAlertIndicator}
    />
  {/if}

  <main class="sed-main">
    {#if !hasEndpoints}
      <EmptyStateCard
        containerClass="storage-endpoints-empty"
        iconClass="bi bi-hdd-stack"
        title="No storage endpoint"
        description="Storage endpoints are required to discover roots, apply governance, and handle access requests."
        ctaLabel="Create endpoint"
        onCta={() => (showWizard = true)}
        hint="The wizard guides you step by step."
      />
    {:else if selected}
      <EntityConsoleShell>
        <svelte:fragment slot="header">
          <EntityConsoleHeader
            eyebrow="Storage endpoint"
            title={`${endpointName(selected)} Console`}
            subtitle={endpointHost(selected) || endpointZone(selected)}
            metaItems={endpointHeaderMetaItems(selected)}
            statusLabel={healthLabel(endpointHealth(selected))}
            statusTone={endpointOperationalTone(selected)}
            showAttention={false}
            actions={endpointHeaderActions(selected)}
            actionsAriaLabel="Storage endpoint actions"
          />
          <EntityAlertStrip
            items={endpointAlertItems}
            onViewAll={() => (showEndpointAlertsDrawer = true)}
            ariaLabel="Storage endpoint alerts"
          />
        </svelte:fragment>

        <svelte:fragment slot="tabs">
          <EntityTabs
            tabs={endpointTabs}
            activeKey={activeEndpointTab}
            ariaLabel="Storage endpoint sections"
            onChange={handleEndpointTabChange}
          />
        </svelte:fragment>

        {#if activeEndpointTab === 'overview'}
          <EntityOverviewLayout>
            <svelte:fragment slot="main">
              <EntityKpiRow items={kpiItems} ariaLabel="Storage endpoint KPIs" />

              <EntityOverviewPanel title="Governed storage roots" panelClass="sed-panel--governed">
                <AssociatedRootsTable rows={rootsFilteredRows.slice(0, 10)} dense={true} emptyLabel="No associated roots" />
              </EntityOverviewPanel>
            </svelte:fragment>

            <svelte:fragment slot="side">
              <RecentActivityCard
                title="Recent activity"
                items={activity}
                max={5}
                onViewAll={() => (activeEndpointTab = 'activity')}
                onSelect={openActivityDetails}
              />
            </svelte:fragment>
          </EntityOverviewLayout>
        {:else if activeEndpointTab === 'activity'}
          <ActivityTabPanel
            items={activity}
            emptyLabel="No activity available for this endpoint"
            onSelect={openActivityDetails}
          />
        {:else}
          <ProvisioningPolicyScreen
            scope="storage-endpoint"
            title=""
            saveLabel="Save changes"
            configuration={endpointProvisioningViewModel.configuration}
            preview={endpointProvisioningViewModel.preview}
            effective={endpointProvisioningViewModel.effective}
            onSave={saveEndpointProvisioning}
            saveDisabled={!endpointCanSave}
            saveBusy={endpointProvisioningBusy}
            errorMessage={endpointProvisioningError || (provisioningWarnings.length > 0 ? provisioningWarnings.join(' · ') : null)}
            showUnsaved={endpointIsDirty}
            showPreview={endpointProvisioningDraft.policyMode === 'override' || endpointIsDirty}
            showEffectiveSave={endpointProvisioningDraft.policyMode === 'override' || endpointIsDirty}
          />
        {/if}
      </EntityConsoleShell>
    {/if}
  </main>
</div>

<ActivityDetailsDrawer
  open={activityDetailsOpen}
  entry={selectedActivityEntry}
  onClose={closeActivityDetails}
  width="620px"
/>

<EntityAlertDrawer
  open={showEndpointAlertsDrawer}
  onClose={() => (showEndpointAlertsDrawer = false)}
  title="Storage endpoint alerts"
  subtitle={`Endpoint · ${selected ? endpointName(selected) : 'Unavailable'}`}
  items={endpointAlertItems}
  emptyLabel="No alert found for this storage endpoint."
  ariaLabelledby="storage-endpoint-alerts-drawer-title"
/>

<StorageEndpointWizardModal
  open={showWizard}
  onClose={() => (showWizard = false)}
  on:done={async () => {
    showWizard = false;
    toast.success('Storage endpoint created.');
    await invalidateAll();
    await goto('/admin/storage-endpoints');
  }}
/>

<StorageEndpointEditModal
  open={showEditModal}
  endpoint={selected}
  onClose={() => (showEditModal = false)}
  onSaved={async () => {
    showEditModal = false;
    await invalidateAll();
    if (selected) {
      healthLoadedForEndpointId = null;
    }
  }}
/>

<ConfirmActionModal
  open={showDeleteModal}
  onClose={closeDeleteModal}
  onConfirm={removeEndpoint}
  ariaLabelledby="se-detail-delete-modal-title"
  severity="danger"
  title="Delete storage endpoint"
  subtitle={endpointName(endpointToDelete)}
  impactTitle="Impact"
  impactItems={[
    'This endpoint will be permanently deleted.',
    'Probe operations linked to this endpoint will stop.',
    'Dependent governance links will need to be recreated if required.'
  ]}
  cancelLabel="Cancel"
  confirmLabel="Delete"
  confirmBusyLabel="Deleting…"
  busy={deleteBusy}
  requireTextConfirm={true}
  requiredText="DELETE"
  textConfirmLabel="Type"
  textConfirmPlaceholder="DELETE"
/>
