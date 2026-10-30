<script lang="ts">
  import ShareCreateModal from '$lib/components/storage-endpoints/ShareCreateModal.svelte';
  import { alertTitle } from '$lib/mappers/storage-root-alerts.mapper';
  import { t } from '$lib/i18n';
  import { formatActivityItem } from '$lib/activity/format';
  import { formatDateTime } from '$lib/utils/format';
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { goto, invalidateAll } from '$app/navigation';
  import EntityAlertDrawer from '$lib/components/entity/EntityAlertDrawer.svelte';
  import EntityAlertStrip from '$lib/components/entity/EntityAlertStrip.svelte';
  import type { EntityAlertStripItem } from '$lib/components/entity/entity-alerts.types';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import StorageEndpointsSidebar from '$lib/components/storage-endpoints/StorageEndpointsSidebar.svelte';
  import EntityWorkspace from '$lib/components/entity/EntityWorkspace.svelte';
  import StorageEndpointWizardModal from '$lib/components/storage-endpoints/StorageEndpointWizardModal.svelte';
  import StorageEndpointEditModal from '$lib/components/storage-endpoints/StorageEndpointEditModal.svelte';
  import ProvisioningPolicyScreen from '$lib/components/provisioning/ProvisioningPolicyScreen.svelte';
  import {
    buildStorageEndpointProvisioningViewModel,
    type ProvisioningPolicyViewModel
  } from '$lib/components/provisioning/provisioning-policy.adapter';
  import EntityPageHeader from '$lib/components/entity/EntityPageHeader.svelte';
  import EntityStatLine, { type EntityStatItem } from '$lib/components/entity/EntityStatLine.svelte';
  import EntityProperties from '$lib/components/entity/EntityProperties.svelte';
  import EntityProperty from '$lib/components/entity/EntityProperty.svelte';
  import { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';
  import AssociatedRootsTable from '$lib/components/storage-endpoints/AssociatedRootsTable.svelte';
  import ActivityDetailsDrawer from '$lib/components/activity/ActivityDetailsDrawer.svelte';
  import EntityConsoleShell from '$lib/components/entity/EntityConsoleShell.svelte';

  import {
    deleteStorageEndpoint,
    getStorageEndpointProvisioningPolicy,
    putStorageEndpointProvisioningPolicy,
    recordStorageEndpointProbeResult,
    type StorageEndpointProvisioningPolicy,
    type StorageEndpointProvisioningUpdatePayload
  } from '$lib/api/storage-endpoints';
  import {
    buildProvisioningUpdatePayload,
    createProvisioningDraft
  } from '$lib/mappers/storage-endpoint-provisioning.mapper';
  import {
    normalizeProbeStatus,
    reachabilityFromProbeStatus
  } from '$lib/mappers/visual-state.mapper';
  import {
    buildStorageEndpointOperationalAttentionItems,
    endpointHealthToOperationalTone
  } from '$lib/mappers/entity-operational.mapper';
  import type { GovernanceAlert } from '$lib/api/governance-alerts';
  import {
    selectVisibleStorageRootAlertsForRootIds,
    storageRootAlertRootId,
    storageRootAlertSummarySubtitle,
    storageRootAlertTone
  } from '$lib/mappers/storage-root-alerts.mapper';
  import {
    collectStorageRootsAvailabilityByEndpoint,
    type StorageRootAvailabilitySummary
  } from '$lib/jobs/probe-runner';
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from '$lib/jobs/storage-endpoint-probe';
  import { runProbeWithPolling } from '$lib/jobs/probe-runner';
  import { notifyError, toAppError } from '$lib/errors';
  import { logAppError, logInfo, logWarning } from '$lib/logging';
  import { toast } from '$lib/stores/toast';
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
    identitySourceNames?: Record<string, string>;
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
  const endpointName = (ep: any) => String(ep?.name ?? ep?.storage_endpoint_name ?? t('Unavailable'));
  const endpointHost = (ep: any) => String(ep?.host ?? t('Unavailable'));
  const endpointHasHost = (ep: any): boolean => {
    const host = String(ep?.host ?? '').trim();
    return Boolean(host) && host.toLowerCase() !== 'unavailable';
  };
  const endpointZone = (ep: any) => String(ep?.zone?.name ?? ep?.zone_name ?? t('Unavailable'));
  const rootId = (row: any) => Number(row?.id ?? row?.storage_root_id ?? 0);
  const rootName = (row: any) => String(row?.name ?? row?.storage_root_name ?? t('Unavailable'));
  const rootPath = (row: any) => String(row?.root_path ?? row?.path ?? row?.location ?? t('Unavailable'));
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

  const healthLabel = (value: HealthValue): string => {
    if (value === 'healthy') return t('Reachable');
    if (value === 'degraded') return t('Needs review');
    if (value === 'unhealthy') return t('Probe failed');
    return t('No probe yet');
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

  const formatRelativeDate = (value: unknown, fallback = 'Unavailable'): string => {
    const text = String(value ?? '').trim();
    if (!text) return fallback;
    const date = new Date(text);
    if (!Number.isFinite(date.getTime())) return fallback;
    const diffMs = Date.now() - date.getTime();
    if (diffMs < 0) return formatDateTime(text, { empty: t('Unavailable') });
    const seconds = Math.floor(diffMs / 1000);
    if (seconds < 60) return t('Just now');
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return t('{minutes} min ago', { minutes });
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return t('{hours} h ago', { hours });
    const days = Math.floor(hours / 24);
    if (days < 30) return t('{days} day{value} ago', { days, value: (days > 1 ? 's' : '') });
    return formatDateTime(text, { empty: t('Unavailable') });
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

  // The list pane searches by itself (name, host, roots) and highlights the matches
  $: sidebarEndpoints = endpoints;

  $: sidebarGroups = (() => {
    const map = new Map<string, { zone_id: string | number; zone_name: string; endpoints: any[] }>();
    for (const ep of sidebarEndpoints) {
      const zoneName = endpointZone(ep) || t('Unavailable');
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

  const selectSidebarEndpoint = (id: number): void => {
    if (id > 0) goto(`/admin/storage-endpoints/${id}`);
  };

  $: selectedRoots = roots.filter((r) => Number(r?.storage_endpoint_id ?? 0) === selectedId);

  type EndpointTabKey = 'overview' | 'activity' | 'provisioning';
  // Failures of the last 7 days are counted on the Activity tab (the overview no longer lists the activity)
  const isFailure = (entry: any) => ['failed', 'failure', 'error'].includes(String(entry?.outcome ?? entry?.result ?? '').toLowerCase());
  $: recentFailures = activity.filter(
    (entry) => isFailure(entry) && Date.now() - new Date(String(entry?.created_at ?? '')).getTime() < 7 * 24 * 3600 * 1000
  ).length;
  $: endpointTabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    { key: 'activity', label: t('Activity'), icon: 'bi-activity', count: recentFailures || null },
    { key: 'provisioning', label: t('Provisioning'), icon: 'bi-shield-check' }
  ];
  // Last change made by a person (creation, edit…), shown in the Connection card
  $: lastChange = activity.find((entry) => !String(entry?.action ?? '').startsWith('test_'));
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

  // Browser only: during SSR the component fetch cannot resolve relative /api URLs
  $: if (browser && selected && selectedId > 0 && healthLoadedForEndpointId !== selectedId) {
    healthLoadedForEndpointId = selectedId;
    void refreshEndpointHealth(selected);
  }

  $: if (
    browser &&
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
      endpointProvisioningError = String((e as any)?.message ?? t('Unable to load endpoint provisioning policy.'));
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
      toast.success(t('Endpoint provisioning policy updated.'));
      await invalidateAll();
    } catch (e) {
      endpointProvisioningError = String((e as any)?.message ?? t('Unable to save endpoint provisioning policy.'));
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
    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: t('Storage endpoint') });
    const id = probeConfig.endpointId;

    if (!validation.ok) {
      logWarning('Probe blocked: invalid endpoint config', {
        action: 'storage_endpoints.detail.probe.blocked.invalid_config',
        route: `/admin/storage-endpoints/${selectedId}`,
        endpointId: id,
        protocol: probeConfig.protocol,
        message: validation.message
      });
      toast.error(validation.message ?? t('Invalid endpoint probe configuration.'));
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
        toast.success(t('Probe OK for {endpointName}.', { endpointName: endpointName(ep) }));
        await invalidateAll();
      } else {
        await persistEndpointProbeSnapshot(id, {
          last_probe_status: 'failed',
          last_probe_at: probeAt,
          last_probe_message: String(final.errorMessage ?? t('Probe failed'))
        });

        applyAvailabilityHealth(
          id,
          { total: 0, available: 0, unavailable: 0, rows: [] },
          { probeOk: false }
        );
        toast.error(t('Probe failed for {endpointName}.', { endpointName: endpointName(ep) }));
        await invalidateAll();
      }
    } catch (e) {
      const err = toAppError(e, { source: 'ui' });

      await persistEndpointProbeSnapshot(id, {
        last_probe_status: 'failed',
        last_probe_at: new Date().toISOString(),
        last_probe_message: String(err?.message ?? t('Probe failed'))
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
  let showShareModal = false;
  let showEditModal = false;
  let editInitialTab: 'endpoint' | 'roots' = 'endpoint';
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
      toast.success(t('Storage endpoint deleted.'));
      closeDeleteModal();
      await goto('/admin/storage-endpoints');
    } catch (e) {
      if (isDependencyDeleteError(e)) {
        toast.error(dependencyDeleteMessage('storage endpoint', 'storage roots'));
        closeDeleteModal();
        return;
      }
      toast.error((e as any)?.message ?? t('Unable to delete endpoint.'));
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

  // Open alerts per storage root, for the state column of the table
  $: rootAlertCounts = selectVisibleStorageRootAlertsForRootIds(
    selectedRoots.map((row) => rootId(row)),
    data.storageRootAlerts ?? []
  ).reduce<Record<string, number>>((counts, alert) => {
    const key = String(storageRootAlertRootId(alert));
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});

  const rootProbeHealth = (row: any): HealthValue => {
    const own = statusToHealth(String(row?.last_probe_status ?? row?.probe_status ?? ''));
    return own !== 'unknown' ? own : endpointHealth(selected) === 'unhealthy' ? 'unhealthy' : 'unknown';
  };

  $: rootsFilteredRows = selectedRoots
    .map((row) => ({
      id: rootId(row),
      name: String(rootName(row) || '').replace(/^\s*\[[^\]]+\]\s*/, ''),
      path: rootPath(row),
      pendingCount: pendingCountForRoot(row),
      // Result of the root's own last test (as on the Storage roots page), not its availability for requests
      health: rootProbeHealth(row),
      alertCount: rootAlertCounts[String(rootId(row))] ?? 0
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
    return raw ? formatRelativeDate(raw, 'No probe data') : t('No probe data');
  };

  // Internal result codes (endpoint_alive_via_successful_root_probe…) are not shown as such
  const PROBE_MESSAGE_CODES: Record<string, () => string> = {
    endpoint_alive_via_successful_root_probe: () => t('Reachable (a storage root test passed)')
  };

  const endpointLastResultLabel = (ep: any): string => {
    const message = String(ep?.last_probe_message ?? '').trim();
    if (/^[a-z0-9_]+$/.test(message)) {
      return PROBE_MESSAGE_CODES[message]?.() ?? (endpointHealth(ep) === 'healthy' ? t('Reachable') : t('Unreachable'));
    }
    if (message) return message;
    return endpointHealth(ep) === 'healthy' ? t('Reachable') : t('Unreachable');
  };

  const unavailableRootDetails = (endpointIdValue: number): string[] => {
    const rows = Object.entries(rootHealthByEndpointId[String(endpointIdValue)] ?? {})
      .filter(([, health]) => health !== 'healthy')
      .map(([id]) => {
        const row = selectedRoots.find((candidate) => rootId(candidate) === Number(id));
        return row ? rootName(row) : t('Root #{id}', { id });
      });

    return rows.slice(0, 3);
  };

  const endpointHealthDetail = (ep: any): string | null => {
    const health = endpointHealth(ep);
    const lastResult = endpointLastResultLabel(ep);

    if (health === 'healthy') return null;
    if (health === 'unknown') return t('run a probe or refresh status to collect the latest result');
    if (health === 'unhealthy') return lastResult || t('last probe failed');

    const unavailableRoots = unavailableRootDetails(endpointId(ep));
    if (unavailableRoots.length > 0) {
      return t('endpoint probe is reachable, but unavailable roots need review ({join})', { join: unavailableRoots.join(', ') });
    }

    return lastResult || t('probe or configuration needs review');
  };

  let kpiItems: EntityStatItem[] = [];
  $: kpiItems = selected
    ? [
        {
          key: 'roots',
          label: t('Governed storage roots'),
          value: selectedRoots.length,
          big: true
        },
        {
          key: 'pending',
          label: t('Pending requests'),
          value: endpointPendingCount(selected),
          big: true,
          note: endpointPendingCount(selected) > 0 ? t('Requests awaiting review') : t('No pending requests')
        },
        {
          key: 'test',
          label: t('Last test'),
          value: endpointLastProbeLabel(selected),
          hint: endpointLastResultLabel(selected)
        },
        {
          key: 'alerts',
          label: t('Open alerts'),
          value: endpointAlertItems.length > 0 ? t('{count} open', { count: endpointAlertItems.length }) : t('No open alert'),
          hint: endpointAlertItems.length > 0 ? t('Open in Observability') : t('Nothing to review'),
          tone: endpointAlertItems.length > 0 ? 'warning' as const : undefined,
          // The full list, with acknowledge / resolve, is in Observability
          href: `/observability?tab=alerts&q=${encodeURIComponent(endpointName(selected))}`
        }
      ]
    : [];

  $: provisioningWarnings = endpointProvisioningPolicy?.warnings?.map((w) => String(w?.message ?? '').trim()).filter(Boolean) ?? [];

  const endpointOperationalTone = (ep: any) => endpointHealthToOperationalTone(endpointHealth(ep));

  const pillTone = (tone: string): 'success' | 'warning' | 'danger' | 'neutral' =>
    tone === 'success' || tone === 'warning' || tone === 'danger' ? tone : 'neutral';

  const endpointAttentionItems = (ep: any, options?: { includeProvisioningWarnings?: boolean }): string[] =>
    buildStorageEndpointOperationalAttentionItems({
      healthLabel: healthLabel(endpointHealth(ep)),
      healthDetail: endpointHealthDetail(ep),
      hostReady: endpointHasHost(ep),
      hostLabel: endpointHost(ep),
      // Pending requests have their own indicator: they are not an alert of the file server
      pendingRequestCount: 0,
      provisioningWarnings: options?.includeProvisioningWarnings ? provisioningWarnings : []
    });

  // Attention items are translated sentences: compare with the translated error sentences
  const endpointAlertToneFromText = (value: string): 'warning' | 'error' => {
    const text = String(value ?? '');
    const errors = [t('Endpoint is currently unreachable.'), healthLabel('unhealthy'), t('Endpoint host is missing.'),
                    t('Endpoint host is missing: {hostLabel}', { hostLabel: '' })];
    return errors.some((prefix) => prefix && text.startsWith(prefix.replace(/[.:]\s*$/, ''))) ? 'error' : 'warning';
  };

  const operationalAlertItemsForEndpoint = (ep: any, options?: { includeProvisioningWarnings?: boolean }): EntityAlertStripItem[] =>
    endpointAttentionItems(ep, options).map((item, index) => ({
      key: `endpoint-operational-alert-${endpointId(ep)}-${index}-${item}`,
      title: item,
      subtitle: null,
      tone: endpointAlertToneFromText(item)
    }));

  const rootGovernanceAlertItemsForEndpoint = (ep: any): EntityAlertStripItem[] => {
    const endpointRoots = rootsForEndpoint(ep);
    const rootIds = endpointRoots.map((row) => rootId(row));
    const rootLabels = new Map(endpointRoots.map((row) => [rootId(row), rootName(row)]));
    return selectVisibleStorageRootAlertsForRootIds(rootIds, data.storageRootAlerts ?? []).map((alert) => {
      const alertRootId = storageRootAlertRootId(alert);
      const rootLabel = rootLabels.get(alertRootId) ?? t('Storage root #{alertRootId}', { alertRootId });
      const detail = storageRootAlertSummarySubtitle(alert);
      return {
        key: `endpoint-root-alert-${endpointId(ep)}-${String(alert?.alert_key ?? alert?.id ?? `${alert?.alert_type ?? 'alert'}-${alertRootId}`)}`,
        title: alertTitle(alert),
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
      label: t('{count} alert{value}', { count: items.length, value: (items.length > 1 ? 's' : '') })
    };
  };

  // Health, probe and refresh state are read inside the helpers: list them so Svelte recomputes
  $: healthState = [endpointHealthById, rootHealthByEndpointId, healthLoadingByEndpointId,
                    manualHealthRefreshByEndpointId, probingEndpointId];
  $: endpointAlertItems = ((..._deps: unknown[]) =>
    selected ? buildStorageEndpointAlerts(selected, { includeProvisioningWarnings: true }) : [])(healthState);

  const endpointHeaderActions = (ep: any): EntityActionItem[] => [
    {
      key: 'edit',
      label: t('Edit'),
      icon: 'bi-pencil',
      variant: 'secondary',
      onClick: () => (showEditModal = true)
    },
    {
      key: 'probe',
      label: probingEndpointId === endpointId(ep) ? t('Probe running...') : t('Run probe'),
      icon: probingEndpointId === endpointId(ep) ? 'bi-arrow-repeat sed-spin' : 'bi-activity',
      variant: 'primary',
      disabled: probingEndpointId === endpointId(ep),
      onClick: () => runEndpointProbe(ep)
    },
    {
      key: 'delete',
      label: t('Delete storage endpoint'),
      icon: 'bi-trash',
      variant: 'danger',
      overflow: true,
      onClick: () => openDeleteModal(ep)
    }
  ];

  let endpointProvisioningViewModel: ProvisioningPolicyViewModel =
    buildStorageEndpointProvisioningViewModel(null);

  $: {
    const policy = endpointProvisioningPolicy;
    const draft = endpointProvisioningDraft;

    const computedPolicy = policy
      ? {
          ...policy,
          policy_mode: draft.policyMode,
          policy_source: draft.policyMode === 'override' ? 'endpoint' : policy.policy_source,
          policy_source_label:
            draft.policyMode === 'override' ? t('Endpoint override') : policy.policy_source_label,
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
          }
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

{#if !hasEndpoints}
<div class="sed-layout sed-layout--empty">
  <main class="sed-main">
      <EmptyState
        containerClass="storage-endpoints-empty"
        iconClass="bi bi-hdd-stack"
        title={t('No storage endpoint')}
        description={t('Storage endpoints are required to discover roots, apply governance, and handle access requests.')}
        ctaLabel={t('Create endpoint')}
        onCta={() => (showWizard = true)}
        hint={t('The wizard guides you step by step.')}
      />
  </main>
</div>
{:else}
<ShareCreateModal open={showShareModal} endpointId={selectedEndpointId()} onClose={() => (showShareModal = false)} onCreated={() => void invalidateAll()} />
<a class="ep-back" href="/admin/storage-endpoints"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All servers')}</a>
<EntityWorkspace title={t('Storage endpoints')}>
  <svelte:fragment slot="list">
    <StorageEndpointsSidebar
      onAdd={() => (showWizard = true)}
      addLabel={t('New endpoint')}
      query={search}
      groups={sidebarGroups}
      selectedEndpointId={selectedId}
      {roots}
      onSelectEndpoint={selectSidebarEndpoint}
      onQueryChange={(value) => (search = value)}
      {endpointId}
      {endpointName}
      {endpointHost}
      {endpointTone}
      {endpointAlertCount}
      {endpointAlertIndicator}
    />
  </svelte:fragment>
    {#if selected}
      <EntityConsoleShell>
        <svelte:fragment slot="header">
          {#key healthState}
          <EntityPageHeader
            crumbs={[t('Storage endpoints'), endpointZone(selected)]}
            title={endpointName(selected)}
            code={endpointHasHost(selected) ? endpointHost(selected) : t('No host configured')}
            statusLabel={healthLabel(endpointHealth(selected))}
            statusTone={pillTone(endpointOperationalTone(selected))}
            actions={endpointHeaderActions(selected)}
            actionsAriaLabel={t('Storage endpoint actions')}
          />
          <EntityAlertStrip
            items={endpointAlertItems}
            onViewAll={() => (showEndpointAlertsDrawer = true)}
            ariaLabel={t('Storage endpoint alerts')}
            action={!['unhealthy', 'degraded'].includes(endpointHealth(selected)) ? null : { label: t('Edit the connection'), icon: 'bi-pencil', onClick: () => (showEditModal = true) }}
          />
          <EntityStatLine items={kpiItems} ariaLabel={t('Storage endpoint KPIs')} />
          {/key}
        </svelte:fragment>

        <svelte:fragment slot="tabs">
          <Tabs
            tabs={endpointTabs}
            activeKey={activeEndpointTab}
            ariaLabel={t('Storage endpoint sections')}
            onChange={handleEndpointTabChange}
          />
        </svelte:fragment>

        {#if activeEndpointTab === 'overview'}
          <div class="sed-overview">
            <section class="sed-overview__main" aria-label={t('Governed storage roots')}>
              <div class="sed-overview__head">
                <h2>{t('Governed storage roots')}</h2>
                <button type="button" class="b2s-panel__link" on:click={() => (showShareModal = true)}>{t('Create a share')}</button>
                <button type="button" class="b2s-panel__link" on:click={() => { editInitialTab = 'roots'; showEditModal = true; }}>{t('Discover and add')}</button>
              </div>
              <AssociatedRootsTable rows={rootsFilteredRows} dense={true} emptyLabel={t('No associated roots')} />
            </section>

            <EntityProperties title={t('Connection')}>
              <EntityProperty label={t('Host')} mono>{endpointHasHost(selected) ? endpointHost(selected) : '—'}{selected?.port ? `:${selected.port}` : ''}</EntityProperty>
              <EntityProperty label={t('Protocol')}>{String(selected?.protocol ?? selected?.storage_endpoint_type ?? 'SMB').toUpperCase()}</EntityProperty>
              <EntityProperty label={t('Service account')} mono>{selected?.bind_dn || selected?.auth_username || '—'}</EntityProperty>
              <EntityProperty label={t('Identity source')}>{selected?.identity_source_id ? (data.identitySourceNames?.[String(selected.identity_source_id)] || `#${selected.identity_source_id}`) : t('None')}</EntityProperty>
              <EntityProperty label={t('Zone')}>{endpointZone(selected)}</EntityProperty>
              {#if lastChange}
                <EntityProperty label={t('Last change')}>
                  <button type="button" class="sed-link" on:click={() => (activeEndpointTab = 'activity')}>{formatActivityItem(lastChange).title}</button>
                  <small class="sed-muted">{lastChange.actor_display ?? t('System')} · {formatRelativeDate(lastChange.created_at, '')}</small>
                </EntityProperty>
              {/if}
            </EntityProperties>
          </div>
        {:else if activeEndpointTab === 'activity'}
          <ActivityTabPanel
            items={activity}
            emptyLabel={t('No activity available for this endpoint')}
            onSelect={openActivityDetails}
          />
        {:else}
          <ProvisioningPolicyScreen
            scope="storage-endpoint"
            saveLabel={t('Save changes')}
            configuration={{ ...endpointProvisioningViewModel.configuration, zoneLabel: endpointZone(selected) }}
            effective={endpointProvisioningViewModel.effective}
            previewTarget={{ storage_endpoint_id: endpointId(selected) }}
            onSave={saveEndpointProvisioning}
            saveDisabled={!endpointCanSave}
            saveBusy={endpointProvisioningBusy}
            errorMessage={endpointProvisioningError || (provisioningWarnings.length > 0 ? provisioningWarnings.join(' · ') : null)}
            showUnsaved={endpointIsDirty}
          />
        {/if}
      </EntityConsoleShell>
    {/if}
</EntityWorkspace>
{/if}

<ActivityDetailsDrawer
  open={activityDetailsOpen}
  entry={selectedActivityEntry}
  onClose={closeActivityDetails}
/>

<EntityAlertDrawer
  open={showEndpointAlertsDrawer}
  onClose={() => (showEndpointAlertsDrawer = false)}
  title={t('Storage endpoint alerts')}
  subtitle={t('Endpoint · {value}', { value: (selected ? endpointName(selected) : t('Unavailable')) })}
  items={endpointAlertItems}
  emptyLabel={t('No alert found for this storage endpoint.')}
  ariaLabelledby="storage-endpoint-alerts-drawer-title"
/>

<StorageEndpointWizardModal
  open={showWizard}
  onClose={() => (showWizard = false)}
  on:done={async () => {
    showWizard = false;
    toast.success(t('Storage endpoint created.'));
    await invalidateAll();
    await goto('/admin/storage-endpoints');
  }}
/>

<StorageEndpointEditModal
  open={showEditModal}
  endpoint={selected}
  initialTab={editInitialTab}
  onClose={() => { showEditModal = false; editInitialTab = 'endpoint'; }}
  onSaved={async () => {
    showEditModal = false;
    editInitialTab = 'endpoint';
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
  title={t('Delete storage endpoint')}
  subtitle={endpointName(endpointToDelete)}
  impactTitle={t('Impact')}
  impactItems={[
    t('This endpoint will be permanently deleted.'),
    t('Probe operations linked to this endpoint will stop.'),
    t('Dependent governance links will need to be recreated if required.')
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Delete')}
  confirmBusyLabel={t('Deleting…')}
  busy={deleteBusy}
  requireTextConfirm={true}
  requiredText=DELETE
  textConfirmLabel={t('Type')}
  textConfirmPlaceholder=DELETE
/>

<style>
  .sed-link {
    padding: 0;
    border: none;
    background: none;
    color: var(--b2s-color-info);
    font-size: inherit;
    text-align: left;
    cursor: pointer;
  }

  .sed-muted {
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .sed-overview {
    display: flex;
    flex-wrap: wrap;
    gap: 40px;
    align-items: flex-start;
  }

  .sed-overview__main {
    flex: 999 1 420px;
    min-width: 0;
    display: grid;
    gap: 12px;
  }

  .sed-overview__head {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .sed-overview__head h2 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .ep-back {
    position: relative;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin: 16px 0 -14px 28px;
    font-size: 13px;
    color: var(--b2s-color-text-muted);
    text-decoration: none;
  }

  .ep-back:hover {
    color: var(--b2s-color-text);
  }
</style>
