<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { goto, invalidate } from '$app/navigation';
  import SearchField from '$lib/components/common/SearchField.svelte';
  import DualListPicker from '$lib/components/common/DualListPicker.svelte';
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import EntityAlertDrawer from '$lib/components/common/EntityAlertDrawer.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import { attachTagToStorageRoot, detachTagFromStorageRoot } from '$lib/api/tags';
  import { createActivityEvent, listActivityByTarget } from '$lib/api/activity';
  import { listStorageRootGovernanceAlerts, type GovernanceAlert } from '$lib/api/governance-alerts';
  import {
    createStorageRoot,
    deleteStorageRoot,
    getStorageRootOwners,
    recordStorageRootProbeResult,
    updateStorageRoot,
    updateStorageRootOwners,
    type StorageRootOwner,
    type StorageRootCreatePayload,
    type StorageRootUpdatePayload
  } from '$lib/api/storage-roots';
  import {
    buildGovernanceDraftFromOwners,
    buildOwnersUpdatePayload,
    governanceOwnersDraftForRole as buildGovernanceOwnersDraftForRole,
    hasGovernanceDraftChanges,
    mergeBrowserSelectionIntoDraft,
    normalizeAssignedRole,
    normalizeOwnerIds,
    removeOwnerFromDraft,
    shouldResetGovernanceDraftFromOwners,
    type GovernanceOwnerDraft
  } from '$lib/utils/storage-root-governance';
  import {
    applyOwnersBrowserSelectionToDraft,
    type OwnersBrowserSelectionEvent
  } from '$lib/components/storage-roots/storage-root-owners.browser';
  import { toggleSetValue } from '$lib/utils/selection';
  import { normalizeTagsCatalog, tagColor, tagId, tagLabel, type UiTag } from '$lib/utils/tags';
  import { normalizeStorageRootDetailModel, type StorageRootDetailModel } from '$lib/types/storage-roots';
  import {
    normalizeStorageRootRow,
    type StorageRootRow,
    type StorageRootTagLike
  } from '$lib/utils/storage-roots';
  import {
    endpointIdOf,
    endpointNameOf,
    endpointProtocolOf,
    endpointZoneIdOf,
    rootLabelFromPath
  } from '$lib/services/mappers/storage-roots.mapper';
  import {
    buildStorageRootAccessModelRows,
    displayStorageRootTags,
    effectiveAccessUsersByLevel,
    formatDateTimeLabel,
    isSelectedStorageRootRow,
    ownerDisplayName,
    storageRootEndpointLabel,
  } from '$lib/services/mappers/storage-root-detail.mapper';
  import {
    normalizeStorageRootAvailability,
    rootAvailabilityLabel,
    rootAvailabilityVariant,
    type RootAvailability
  } from '$lib/services/mappers/entity-status.mapper';
  import {
    visibleStorageRootAlerts,
    selectOpenStorageRootAlerts,
    storageRootAlertSummarySubtitle,
    storageRootAlertRootId,
    storageRootAlertTone,
    storageRootOpenAlertSummary
  } from '$lib/services/mappers/storage-root-alerts.mapper';
  import { toast } from '$lib/utils/toast';
  import { dependencyDeleteMessage, isDependencyDeleteError } from '$lib/utils/delete-guard';
  import { apiGetData } from '$lib/api/client';
  import { selectionStore } from '$lib/stores/app/selection.store';
  import {
    storageRootsUiStore,
    type StorageRootsDetailTab
  } from '$lib/stores/features/storageRootsUi.store';
  import StorageRootEffectiveAccessModal from '$lib/components/storage-roots/StorageRootEffectiveAccessModal.svelte';
  import StorageRootOwnersAdModal from '$lib/components/storage-roots/StorageRootOwnersAdModal.svelte';
  import AddStorageRootModal from '$lib/components/storage-roots/AddStorageRootModal.svelte';
  import { runProbeWithPolling, syncStorageRootDiscoveryForEndpoint } from '$lib/probe/probe-runner';
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    buildStorageRootProbeRequest,
    parseStorageEndpointProbeRoots,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from '$lib/probe/storage-endpoint-probe';
  import { runProbeWithUi } from '$lib/probe/probe-ui';
  import StorageRootFormModal from '$lib/components/storage-roots/StorageRootFormModal.svelte';
  import StorageRootDrawerShell from '$lib/components/storage-roots/StorageRootDrawerShell.svelte';
  import StorageRootGovernanceDrawer from '$lib/components/storage-roots/StorageRootGovernanceDrawer.svelte';
  import StorageRootTreePanel from '$lib/components/storage-roots/StorageRootTreePanel.svelte';
  import StorageRootDetailView from '$lib/components/storage-roots/StorageRootDetailView.svelte';
  import StorageRootLoadingState from '$lib/components/storage-roots/StorageRootLoadingState.svelte';
  import StorageRootEmptyState from '$lib/components/storage-roots/StorageRootEmptyState.svelte';
  import ConfirmDeleteDialog from '$lib/components/common/ConfirmDeleteDialog.svelte';
  import { showApiErrorToast } from '$lib/core/errors/api-toast';
  import type { AddRootFolder, AddRootZone } from '$lib/components/storage-roots/add-storage-root.types';
  import { canDeleteManagedObject } from '$lib/utils/permissions';

  export let data: {
    user?: {
      id?: string | number;
      is_admin?: boolean;
      roles?: string[];
      display_name?: string | null;
      username?: string | null;
      email?: string | null;
    };
    storageRoots: StorageRootRow[];
    tags: StorageRootTagLike[];
    endpoints?: unknown[];
    storageRootAlerts?: GovernanceAlert[];
    storageRootActivity?: Array<Record<string, unknown>>;
    storageRootActivityRootId?: number | null;
  };

  const PROBE_SYNC_EVENT = 'b2s:storage-endpoint-probe-updated';

  const hasRoots = () => (data.storageRoots ?? []).length > 0;

  const refreshStorageRootsLoad = async () => {
    await Promise.all([
      invalidate('app:storage-roots'),
      invalidate('app:storage-endpoints'),
      invalidate('app:tags'),
      invalidate('app:governance-alerts')
    ]);
  };

  let probeSyncRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  const applyEndpointProbeSyncLocally = (detail: {
    endpoint_id?: number;
    last_probe_status?: string;
    last_probe_at?: string;
    last_probe_message?: string | null;
  }) => {
    const endpointId = Number(detail?.endpoint_id ?? 0);
    if (!Number.isFinite(endpointId) || endpointId <= 0) return false;

    const nextStatus = String(detail?.last_probe_status ?? '').trim().toLowerCase();
    const nextProbeAt = String(detail?.last_probe_at ?? '').trim() || null;
    const nextProbeMessage = detail?.last_probe_message ?? null;

    let matched = false;

    const endpointRows = Array.isArray(data.endpoints) ? data.endpoints : [];
    if (endpointRows.length > 0) {
      data = {
        ...data,
        endpoints: endpointRows.map((endpoint: any) => {
          const currentEndpointId = Number(endpoint?.storage_endpoint_id ?? endpoint?.id ?? 0);
          if (currentEndpointId !== endpointId) return endpoint;
          matched = true;
          return {
            ...endpoint,
            last_probe_status: nextStatus,
            last_probe_at: nextProbeAt,
            last_probe_message: nextProbeMessage
          };
        })
      };
    }

    const storageRootRows = Array.isArray(data.storageRoots) ? data.storageRoots : [];
    const affectedRootIds: number[] = [];
    if (storageRootRows.length > 0) {
      data = {
        ...data,
        storageRoots: storageRootRows.map((row: any) => {
          const rowEndpointId = Number(row?.storage_endpoint_id ?? row?.endpoint_id ?? 0);
          if (rowEndpointId !== endpointId) return row;
          matched = true;
          const rowId = Number(row?.storage_root_id ?? row?.id ?? 0);
          if (Number.isFinite(rowId) && rowId > 0) affectedRootIds.push(rowId);
          return {
            ...row,
            storage_endpoint_last_probe_status: nextStatus,
            storage_endpoint_last_probe_at: nextProbeAt,
            storage_endpoint_last_probe_message: nextProbeMessage
          };
        })
      };
    }

    invalidateDetailsCacheForRoots(affectedRootIds);

    if (
      overview &&
      Number(overview?.storage_endpoint_id ?? overview?.storage_endpoint?.id ?? 0) === endpointId
    ) {
      const overviewRootId = Number((overview as any)?.storage_root_id ?? (overview as any)?.id ?? 0);
      if (Number.isFinite(overviewRootId) && overviewRootId > 0) {
        setOverviewForRoot(
          overviewRootId,
          {
            ...(overview as Record<string, unknown>),
            storage_endpoint_last_probe_status: nextStatus,
            storage_endpoint_last_probe_at: nextProbeAt,
            storage_endpoint_last_probe_message: nextProbeMessage,
            storage_endpoint: {
              ...((overview as any)?.storage_endpoint ?? {}),
              last_probe_status: nextStatus,
              last_probe_at: nextProbeAt,
              last_probe_message: nextProbeMessage
            }
          },
          { selectedRootId: selectedStorageRootId }
        );
      }
    }

    return matched;
  };

  onMount(() => {
    if (!browser) return;

    const onProbeSync = (event: Event) => {
      const custom = event as CustomEvent<{
        endpoint_id?: number;
        last_probe_status?: string;
        last_probe_at?: string;
        last_probe_message?: string | null;
      }>;

      const applied = applyEndpointProbeSyncLocally(custom?.detail ?? {});
      if (!applied) return;

      if (probeSyncRefreshTimer) clearTimeout(probeSyncRefreshTimer);
      probeSyncRefreshTimer = setTimeout(() => {
        void refreshStorageRootsLoad();

        const selectedEndpointId = Number(selectedRow?.storage_endpoint_id ?? 0);
        const eventEndpointId = Number(custom?.detail?.endpoint_id ?? 0);
        const selectedRootId = Number(selectedStorageRootId ?? 0);
        if (
          selectedRootId > 0 &&
          selectedEndpointId > 0 &&
          selectedEndpointId === eventEndpointId
        ) {
          void invalidateAndReloadDetailsForRoot(selectedRootId);
        }
      }, 180);
    };

    window.addEventListener(PROBE_SYNC_EVENT, onProbeSync as EventListener);
    return () => {
      window.removeEventListener(PROBE_SYNC_EVENT, onProbeSync as EventListener);
    };
  });

  onDestroy(() => {
    if (probeSyncRefreshTimer) {
      clearTimeout(probeSyncRefreshTimer);
      probeSyncRefreshTimer = null;
    }
  });

  /* -------------------------------------------------------------------------- */
  /* Sidebar + selection                                                        */
  /* -------------------------------------------------------------------------- */

  let selectedStorageRootId: number | null = null;
  let selectedRow: StorageRootRow | null = null;
  let lastAppliedSelectedParam: number | null = null;

  $: ctxRows = (data.storageRoots ?? []).map(normalizeStorageRootRow);

  $: if (browser && ctxRows.length > 0) {
    const selectedParam = Number($page.url.searchParams.get('selected') ?? 0);
    if (Number.isFinite(selectedParam) && selectedParam > 0 && selectedParam !== lastAppliedSelectedParam) {
      const exists = ctxRows.some((r) => Number(r.storage_root_id) === selectedParam);
      if (exists && selectedStorageRootId !== selectedParam) {
        selectedStorageRootId = selectedParam;
      }
      lastAppliedSelectedParam = selectedParam;
    }
  }

  $: if (!selectedStorageRootId && ctxRows.length > 0) {
    selectedStorageRootId = ctxRows[0].storage_root_id;
  }

  $: if (selectedStorageRootId && !ctxRows.some((r) => r.storage_root_id === selectedStorageRootId)) {
    selectedStorageRootId = ctxRows.length > 0 ? ctxRows[0].storage_root_id : null;
  }

  $: selectedRow = selectedStorageRootId
    ? ctxRows.find((r) => r.storage_root_id === selectedStorageRootId) ?? null
    : null;

  $: if (selectedStorageRootId !== $selectionStore.selectedStorageRootId) {
    selectionStore.setSelectedStorageRootId(selectedStorageRootId);
  }

  $: if (selectedStorageRootId !== $storageRootsUiStore.selectedStorageRootId) {
    storageRootsUiStore.setSelectedStorageRootId(selectedStorageRootId);
  }

  const selectRoot = (id: number) => {
    if (selectedStorageRootId === id) return;
    selectedStorageRootId = id;
    selectionStore.setSelectedStorageRootId(id);
    storageRootsUiStore.setSelectedStorageRootId(id);
    storageRootsUiStore.setDetailTab('overview');
    void loadStorageRootActivity(id);
  };

  /* -------------------------------------------------------------------------- */
  /* Details load                                                               */
  /* -------------------------------------------------------------------------- */

  let overview: StorageRootDetailModel | null = null;
  let detailsLoading = false;
  const detailsCache = new Map<number, StorageRootDetailModel>();
  let detailsRequestToken = 0;

  const invalidateDetailsCacheForRoots = (rootIds: number[]) => {
    for (const rootId of rootIds) {
      detailsCache.delete(rootId);
    }
  };

  const setOverviewForRoot = (
    rootId: number,
    payload: Record<string, unknown>,
    options?: { selectedRootId?: number | null }
  ) => {
    const requestedSelectedRootId = Number(options?.selectedRootId ?? rootId);
    const normalizedSelectedRootId =
      Number.isFinite(requestedSelectedRootId) && requestedSelectedRootId > 0
        ? requestedSelectedRootId
        : undefined;
    const nextOverview = normalizeStorageRootDetailModel(payload, {
      selectedRootId: normalizedSelectedRootId
    });
    overview = nextOverview;
    detailsCache.set(rootId, nextOverview);
    return nextOverview;
  };

  async function loadDetails(id: number) {
    const token = ++detailsRequestToken;

    const cached = detailsCache.get(id);
    if (cached) {
      overview = cached;
      detailsLoading = false;
    } else {
      detailsLoading = true;
    }

    try {
      const [base, groupsPayload, ownersPayload, alertsPayload] = await Promise.all([
        apiGetData<Record<string, unknown>>(fetch, `/storage-roots/${id}/overview`),
        apiGetData<{ groups?: unknown[] }>(fetch, `/storage-roots/${id}/ad-groups?include_members=1&include_expected=1`).catch(() => null),
        getStorageRootOwners(fetch, id).catch(() => []),
        listStorageRootGovernanceAlerts(fetch, id, { status: 'open', reconcile: true }).catch(() => [])
      ]);
      if (token !== detailsRequestToken) return;

      const owners = Array.isArray(ownersPayload)
        ? ownersPayload
        : (Array.isArray(base?.owners) ? (base.owners as any[]) : []);
      const openAlerts = visibleStorageRootAlerts(Array.isArray(alertsPayload) ? alertsPayload : []);

      setOverviewForRoot(id, {
        ...(base ?? {}),
        owners,
        projected_ad_groups: Array.isArray(groupsPayload?.groups)
          ? groupsPayload.groups
          : (Array.isArray(base?.projected_ad_groups) ? base.projected_ad_groups : []),
        recent_activity: Array.isArray(base?.recent_activity) ? base.recent_activity : [],
        governance_alerts: openAlerts,
        open_alerts_count: openAlerts.length,
        open_alerts_error_count: openAlerts.filter((alert) => storageRootAlertTone(alert) === 'error').length
      });
      mergeStorageRootAlerts(id, openAlerts);
    } catch {
      if (token !== detailsRequestToken) return;
      overview = null;
    } finally {
      if (token === detailsRequestToken) {
        detailsLoading = false;
      }
    }
  }

  const invalidateAndReloadDetailsForRoot = async (rootId: number | null | undefined) => {
    const normalizedRootId = Number(rootId ?? 0);
    if (!Number.isFinite(normalizedRootId) || normalizedRootId <= 0) return;
    detailsCache.delete(normalizedRootId);
    await loadDetails(normalizedRootId);
  };

  let detailsLoadedForRootId: number | null = null;

  $: {
    const currentRootId = Number(selectedStorageRootId ?? 0);
    if (currentRootId > 0 && currentRootId !== detailsLoadedForRootId) {
      detailsLoadedForRootId = currentRootId;
      void loadDetails(currentRootId);
    }
    if (currentRootId <= 0) {
      detailsLoadedForRootId = null;
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Read helpers                                                               */
  /* -------------------------------------------------------------------------- */

  const selectedEndpoint = () => {
    const endpointId = Number(selectedRow?.storage_endpoint_id ?? 0);
    if (!Number.isFinite(endpointId) || endpointId <= 0) return null;
    const rows = Array.isArray(data.endpoints) ? data.endpoints : [];
    return rows.find((ep: any) => Number(ep?.storage_endpoint_id ?? ep?.id ?? 0) === endpointId) ?? null;
  };

  const endpointLabel = () => storageRootEndpointLabel(selectedRow, selectedEndpoint());
  const endpointAddressLabel = () => {
    const endpoint: any = selectedEndpoint();
    return String(
      selectedRow?.storage_endpoint_host ??
        selectedRow?.storage_endpoint_hostname ??
        endpoint?.host ??
        endpoint?.hostname ??
        endpoint?.address ??
        endpoint?.ip_address ??
        overview?.storage_endpoint_host ??
        (overview as any)?.storage_endpoint?.host ??
        ''
    ).trim() || endpointLabel();
  };
  const isSelectedRootRow = (row: any): boolean => isSelectedStorageRootRow(row, selectedStorageRootId, overview);

  const endpointProbeStatusForRoot = (row: any) => {
    const endpointId = Number(row?.storage_endpoint_id ?? row?.endpoint_id ?? 0);
    const rows = Array.isArray(data.endpoints) ? data.endpoints : [];
    const endpoint = Number.isFinite(endpointId) && endpointId > 0
      ? rows.find((ep: any) => Number(ep?.storage_endpoint_id ?? ep?.id ?? 0) === endpointId)
      : null;

    const selectedScopedStatus = isSelectedRootRow(row)
      ? String(
        overview?.storage_endpoint?.last_probe_status ??
        overview?.storage_endpoint?.probe_status ??
        endpoint?.last_probe_status ??
        endpoint?.probe_status ??
        ''
      )
        .trim()
        .toLowerCase()
      : '';

    const fallbackStatus =
      row?.storage_endpoint_last_probe_status ??
      row?.storage_endpoint_probe_status ??
      '';

    return String(selectedScopedStatus || fallbackStatus)
      .trim()
      .toLowerCase();
  };

  const endpointProbeTimestampForRoot = (row: any): string | null => {
    const endpointId = Number(row?.storage_endpoint_id ?? row?.endpoint_id ?? 0);
    const rows = Array.isArray(data.endpoints) ? data.endpoints : [];
    const endpoint = Number.isFinite(endpointId) && endpointId > 0
      ? rows.find((ep: any) => Number(ep?.storage_endpoint_id ?? ep?.id ?? 0) === endpointId)
      : null;

    const selectedScopedTimestamp = isSelectedRootRow(row)
      ? (
        overview?.last_probe_at ??
        overview?.probe_last_run_at ??
        row?.last_probe_at ??
        row?.probe_last_run_at ??
        overview?.storage_endpoint?.last_probe_at ??
        endpoint?.last_probe_at ??
        null
      )
      : null;

    const raw =
      selectedScopedTimestamp ??
      row?.last_probe_at ??
      row?.probe_last_run_at ??
      row?.probe_last_at ??
      row?.storage_endpoint_last_probe_at ??
      null;
    return raw ? String(raw) : null;
  };

  const effectiveAvailabilityForRow = (row: any): RootAvailability => {
    const rowId = Number(row?.storage_root_id ?? row?.id ?? 0);
    const runtimeStatus = Number.isFinite(rowId) && rowId > 0
      ? String(rootProbeStateByRootId[rowId]?.status ?? '')
      : '';

    if (runtimeStatus === 'running') return 'checking';
    if (runtimeStatus === 'success') return 'reachable';
    if (runtimeStatus === 'failed') return 'unreachable';

    if (Number(rowId) > 0 && rowId === Number(selectedStorageRootId ?? 0)) {
      const selectedAvailability = normalizeStorageRootAvailability(overview?.effective_availability ?? row?.effective_availability);
      if (selectedAvailability !== 'unknown') return selectedAvailability;
    }

    return normalizeStorageRootAvailability(row?.effective_availability);
  };

  const effectiveUsersByLevel = (level: 'read' | 'write') => effectiveAccessUsersByLevel(overview, level);

  $: guardians = (overview?.owners ?? []).filter((o: any) => normalizeAssignedRole(o?.role) === 'guardian');

  const selectedOverviewReady = () => {
    const overviewRootId = Number(overview?.storage_root_id ?? overview?.id ?? 0);
    return !detailsLoading && overviewRootId > 0 && overviewRootId === Number(selectedStorageRootId ?? 0);
  };

  const rootAvailabilityText = () => {
    if (!selectedRow) return 'Unknown';
    return rootAvailabilityLabel(effectiveAvailabilityForRow(selectedRow));
  };

  const rootAvailabilityTone = (): 'success' | 'warning' | 'error' => {
    if (!selectedRow) return 'warning';
    const variant = rootAvailabilityVariant(effectiveAvailabilityForRow(selectedRow));
    if (variant === 'success') return 'success';
    if (variant === 'error') return 'error';
    return 'warning';
  };

  const lastProbeLabel = () => {
    const raw =
      selectedProbeState().lastRunAt ??
      overview?.last_probe_at ??
      overview?.probe_last_run_at ??
      selectedRow?.last_probe_at ??
      selectedRow?.probe_last_run_at ??
      overview?.storage_endpoint?.last_probe_at ??
      overview?.storage_endpoint_last_probe_at ??
      selectedEndpoint()?.last_probe_at ??
      (selectedRow ? endpointProbeTimestampForRoot(selectedRow) : null) ??
      null;
    if (!raw) return 'Never run';
    return formatDateTimeLabel(raw);
  };

  const accessModelRows = () => buildStorageRootAccessModelRows(overview);

  const displayTags = (row: StorageRootRow | null): StorageRootTagLike[] => displayStorageRootTags(overview, row);

  type StorageRootTreeAlertSummary = { count: number; tone: 'warning' | 'error'; label?: string } | null;
  type StorageRootDetailAlertItem = {
    key: string;
    title: string;
    subtitle?: string | null;
    tone?: 'warning' | 'error';
  };

  function storageRootAlertsForRootId(rootIdRaw: number | string | null | undefined): GovernanceAlert[] {
    return selectOpenStorageRootAlerts({
      rootId: rootIdRaw,
      selectedRow,
      overview: selectedOverviewReady() ? (overview as Record<string, unknown>) : overview,
      globalAlerts: data.storageRootAlerts ?? [],
      detailsLoading
    });
  }

  function mergeStorageRootAlerts(rootIdRaw: number | string | null | undefined, alerts: GovernanceAlert[]) {
    const rootId = Number(rootIdRaw ?? 0);
    if (!Number.isFinite(rootId) || rootId <= 0) return;
    const others = (data.storageRootAlerts ?? []).filter((alert) => storageRootAlertRootId(alert) !== rootId);
    data = {
      ...data,
      storageRootAlerts: [...others, ...alerts]
    };
  }

  const alertItemFromRow = (alert: GovernanceAlert): StorageRootDetailAlertItem => ({
    key: String(alert?.alert_key ?? alert?.id ?? `${alert?.alert_type ?? 'alert'}-${alert?.scope_id ?? ''}`),
    title: String(alert?.title ?? 'Attention required'),
    subtitle: storageRootAlertSummarySubtitle(alert),
    tone: storageRootAlertTone(alert)
  });

  const rootAlertSummary = (row: StorageRootRow): StorageRootTreeAlertSummary => {
    return storageRootOpenAlertSummary(row, data.storageRootAlerts ?? []);
  };

  let selectedRootAlerts: StorageRootDetailAlertItem[] = [];
  $: {
    const selectedAlertRootId = Number(selectedRow?.storage_root_id ?? 0);
    const selectedOverviewRootId = Number(overview?.storage_root_id ?? overview?.id ?? 0);
    const selectedOverviewAlerts = (overview as any)?.governance_alerts;
    const loadedAlerts = data.storageRootAlerts;
    const isLoadingDetails = detailsLoading;

    selectedRootAlerts =
      selectedAlertRootId > 0
        ? storageRootAlertsForRootId(selectedAlertRootId).map(alertItemFromRow)
        : [];

    void selectedOverviewRootId;
    void selectedOverviewAlerts;
    void loadedAlerts;
    void isLoadingDetails;
  }

  const showSelectedStatusBadge = () => {
    const status = rootAvailabilityText();
    return status !== 'Reachable' && status !== 'Unknown';
  };

  const selectDetailTab = (tab: StorageRootsDetailTab) => {
    storageRootsUiStore.setDetailTab(tab);
    if (tab === 'activity' && selectedStorageRootId) {
      void loadStorageRootActivity(Number(selectedStorageRootId));
    }
  };

  /* -------------------------------------------------------------------------- */
  /* CRUD root                                                                   */
  /* -------------------------------------------------------------------------- */

  let rootModalOpen = false;
  let rootModalMode: 'create' | 'edit' | 'delete' = 'create';
  let editingRoot: any | null = null;
  let deleteRootModalOpen = false;

  const canDeleteStorageRoot = () =>
    canDeleteManagedObject(data?.user?.roles);

  function openEditRoot() {
    if (!selectedRow) {
      toast.warning('Select a storage root first');
      return;
    }
    editingRoot = selectedRow;
    rootModalMode = 'edit';
    rootModalOpen = true;
  }

  function openDeleteRoot(root: any) {
    if (!canDeleteStorageRoot()) {
      toast.error('Only administrators can delete storage roots');
      return;
    }
    editingRoot = root;
    deleteRootModalOpen = true;
  }

  async function submitRoot(payload: StorageRootCreatePayload | StorageRootUpdatePayload) {
    try {
      if (rootModalMode === 'edit' && editingRoot?.storage_root_id) {
        await updateStorageRoot(fetch, Number(editingRoot.storage_root_id), payload as StorageRootUpdatePayload);
        toast.success('Storage root updated');
        await goto(`/storage-roots?selected=${Number(editingRoot.storage_root_id)}`, { replaceState: true });
      } else {
        const created = await createStorageRoot(fetch, payload as StorageRootCreatePayload);
        toast.success('Storage root created');
        await goto(`/storage-roots?selected=${created.id}`, { replaceState: true });
      }

      detailsCache.clear();
      rootModalOpen = false;
      await refreshStorageRootsLoad();
      if (selectedStorageRootId) {
        await invalidateAndReloadDetailsForRoot(selectedStorageRootId);
      }
    } catch {
      toast.error('Storage root operation failed');
    }
  }

  async function confirmDeleteRoot() {
    if (!editingRoot?.storage_root_id) return;
    if (!canDeleteStorageRoot()) {
      toast.error('Only administrators can delete storage roots');
      return;
    }

    const deletedRootId = Number(editingRoot.storage_root_id);

    try {
      await deleteStorageRoot(fetch, deletedRootId);
      data = {
        ...data,
        storageRoots: (data.storageRoots ?? []).filter(
          (row: any) => Number(row?.storage_root_id ?? row?.id ?? 0) !== deletedRootId
        ),
        storageRootAlerts: (data.storageRootAlerts ?? []).filter(
          (alert: any) => Number(storageRootAlertRootId(alert) ?? 0) !== deletedRootId
        )
      };
      rootModalOpen = false;
      deleteRootModalOpen = false;
      editingRoot = null;
      detailsCache.clear();
      selectedStorageRootId = null;
      selectionStore.setSelectedStorageRootId(null);
      storageRootsUiStore.setSelectedStorageRootId(null);
      await goto('/storage-roots', { replaceState: true });
      await refreshStorageRootsLoad();
      toast.success('Storage root deleted');
    } catch (e) {
      if (isDependencyDeleteError(e)) {
        rootModalOpen = false;
        deleteRootModalOpen = false;
        editingRoot = null;
        toast.error(dependencyDeleteMessage('storage root', 'dependent records'));
        return;
      }
      showApiErrorToast(e, 'Unable to delete storage root.');
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Add root wizard                                                             */
  /* -------------------------------------------------------------------------- */

  let addRootModalOpen = false;
  let addRootLoading = false;
  let addRootSelectedZoneId: string | number | null = null;
  let addRootSelectedEndpointId: string | number | null = null;
  let addRootSelectedFolderId: string | number | null = null;
  let addRootSelectedFolderIds: Array<string | number> = [];
  let discoveredFoldersByEndpointId: Record<number, AddRootFolder[]> = {};
  let endpointDiscoveryBusyById: Record<string, boolean> = {};
  let endpointDiscoveryStateById: Record<number, { status: 'idle' | 'running' | 'success' | 'failed'; message?: string | null; lastRefreshAt?: string | null }> = {};
  let addRootZones: AddRootZone[] = [];

  function openCreateRoot() {
    const endpointRows = Array.isArray(data.endpoints) ? data.endpoints : [];
    if (endpointRows.length === 0) {
      toast.warning('No storage endpoint available to create a storage root');
      return;
    }

    addRootModalOpen = true;
    addRootSelectedFolderId = null;
    addRootSelectedFolderIds = [];
    addRootSelectedZoneId = addRootZones[0]?.id ?? null;
    addRootSelectedEndpointId = addRootZones[0]?.endpoints?.[0]?.id ?? null;
  }

  const endpointRefreshState = (endpointId: number) =>
    endpointDiscoveryStateById[endpointId] ?? { status: 'idle' as const, message: null, lastRefreshAt: null };

  function rebuildAddRootZones() {
    const endpointRows = Array.isArray(data.endpoints) ? data.endpoints : [];
    const byZone = new Map<string, AddRootZone>();
    const endpointBasePathOf = (endpoint: any): string =>
      String(
        endpoint?.base_path ??
          endpoint?.discovery_base_path ??
          endpoint?.root_path ??
          endpoint?.share_path ??
          endpoint?.path ??
          ''
      ).trim();

    for (const endpoint of endpointRows) {
      const endpointId = endpointIdOf(endpoint);
      const rawZoneId = endpointZoneIdOf(endpoint);
      const zoneId = Number.isFinite(rawZoneId) && rawZoneId > 0 ? rawZoneId : `unassigned-${endpointId}`;
      const key = String(zoneId);
      const zoneName = String(endpoint?.zone_name ?? endpoint?.zone?.name ?? 'Unassigned zone');

      if (!byZone.has(key)) {
        byZone.set(key, {
          id: zoneId,
          name: zoneName,
          discoveryCount: 0,
          endpoints: [],
          discoveredFolders: []
        });
      }

      const zone = byZone.get(key)!;
      const endpointFolders = discoveredFoldersByEndpointId[endpointId] ?? [];
      const endpointEntry = {
        id: endpointId,
        name: endpointNameOf(endpoint),
        zoneName,
        protocol: endpointProtocolOf(endpoint),
        basePath: endpointBasePathOf(endpoint) || null,
        status: endpoint?.status ?? endpoint?.operational_status ?? null,
        host: endpoint?.host ?? endpoint?.hostname ?? null,
        discoveryCount: endpointFolders.length,
        discoveredFolders: endpointFolders,
        refreshing: Boolean(endpointDiscoveryBusyById[String(endpointId)]),
        refreshStatus: endpointRefreshState(endpointId).status,
        refreshMessage: endpointRefreshState(endpointId).message ?? null,
        lastRefreshAt: endpointRefreshState(endpointId).lastRefreshAt ?? null,
        lastProbeAt: endpoint?.last_probe_at ?? endpoint?.probe_at ?? null,
        lastProbeStatus: endpoint?.last_probe_status ?? endpoint?.probe_status ?? null
      };

      zone.endpoints.push(endpointEntry);
      zone.discoveryCount += endpointEntry.discoveryCount;
      zone.discoveredFolders.push(...endpointFolders.map((folder) => ({ ...folder, zoneId: zone.id })));
    }

    addRootZones = Array.from(byZone.values()).sort((a, b) => String(a.name).localeCompare(String(b.name), 'en'));
  }

  async function runDiscoveryForEndpoint(endpoint: any, zoneId: string | number): Promise<AddRootFolder[]> {
    const endpointId = endpointIdOf(endpoint);
    const protocolRaw = String(endpoint?.protocol ?? endpoint?.type ?? endpoint?.storage_endpoint_type ?? '').trim().toLowerCase();
    const protocol = endpointProtocolOf(endpoint);
    const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Storage endpoint' });

    if (!Number.isFinite(endpointId) || endpointId <= 0 || (protocolRaw !== 'smb' && protocolRaw !== 'cifs') || !validation.ok) {
      return discoveredFoldersByEndpointId[endpointId] ?? [];
    }

    const request = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
      discover: true,
      timeoutSec: 30,
      uiOrigin: 'admin'
    });

    const final = await runProbeWithPolling({
      fetchFn: fetch,
      request,
      intervalMs: 1500,
      maxAttempts: 80
    });

    if (!final.ok) {
      throw new Error(final.errorMessage || `Discovery failed for endpoint ${endpointNameOf(endpoint)}`);
    }

    await syncStorageRootDiscoveryForEndpoint(fetch, endpointId, final.result);

    const roots = parseStorageEndpointProbeRoots(final.result);
    return roots.map((rootPath, index) => ({
      id: `probe-${endpointId}-${index}-${rootPath}`,
      zoneId,
      protocol,
      folderName: rootLabelFromPath(rootPath),
      endpointId,
      rootPath
    }));
  }

  async function handleTriggerEndpointDiscovery(zoneId: string | number, endpointIdRaw: string | number) {
    const endpointId = Number(endpointIdRaw ?? 0);
    if (!Number.isFinite(endpointId) || endpointId <= 0) {
      toast.warning('Invalid storage endpoint selected');
      return;
    }

    const endpoint = (Array.isArray(data.endpoints) ? data.endpoints : []).find((row: any) => endpointIdOf(row) === endpointId);
    if (!endpoint) {
      toast.warning('Storage endpoint not found');
      return;
    }

    endpointDiscoveryBusyById = { ...endpointDiscoveryBusyById, [String(endpointId)]: true };
    endpointDiscoveryStateById = {
      ...endpointDiscoveryStateById,
      [endpointId]: {
        status: 'running',
        message: null,
        lastRefreshAt: endpointRefreshState(endpointId).lastRefreshAt ?? null
      }
    };

    try {
      const next = { ...discoveredFoldersByEndpointId };
      const discovered = await runDiscoveryForEndpoint(endpoint, zoneId);
      next[endpointId] = discovered;

      discoveredFoldersByEndpointId = next;
      endpointDiscoveryStateById = {
        ...endpointDiscoveryStateById,
        [endpointId]: {
          status: 'success',
          message: null,
          lastRefreshAt: new Date().toISOString()
        }
      };

      addRootSelectedZoneId = zoneId;
      addRootSelectedEndpointId = endpointId;
      addRootSelectedFolderId = null;
      toast.success(`${discovered.length} storage root(s) found`);
    } catch (e: any) {
      endpointDiscoveryStateById = {
        ...endpointDiscoveryStateById,
        [endpointId]: {
          status: 'failed',
          message: String(e?.message ?? 'Endpoint discovery failed'),
          lastRefreshAt: new Date().toISOString()
        }
      };
      toast.error(e?.message ?? 'Endpoint discovery failed');
    } finally {
      endpointDiscoveryBusyById = { ...endpointDiscoveryBusyById, [String(endpointId)]: false };
    }
  }

  function handleSelectAddRootZone(zoneId: string | number) {
    addRootSelectedZoneId = zoneId;
    const zone = addRootZones.find((z) => String(z.id) === String(zoneId));
    addRootSelectedEndpointId = zone?.endpoints?.[0]?.id ?? null;
    addRootSelectedFolderId = null;
    addRootSelectedFolderIds = [];
  }

  function handleSelectAddRootEndpoint(zoneId: string | number, endpointId: string | number) {
    addRootSelectedZoneId = zoneId;
    addRootSelectedEndpointId = endpointId;
    addRootSelectedFolderId = null;
    addRootSelectedFolderIds = [];
  }

  function handleSelectAddRootFolder(folderId: string | number) {
    addRootSelectedFolderId = folderId;
    if (!addRootSelectedFolderIds.some((value) => String(value) === String(folderId))) {
      addRootSelectedFolderIds = [folderId];
    }
  }

  function handleSelectAddRootFolders(folderIds: Array<string | number>) {
    addRootSelectedFolderIds = folderIds;
    addRootSelectedFolderId = folderIds[0] ?? null;
  }

  function closeAddRootModal() {
    addRootModalOpen = false;
    addRootLoading = false;
    addRootSelectedEndpointId = null;
    addRootSelectedFolderId = null;
    addRootSelectedFolderIds = [];
  }

  const selectedAddRootFolders = (folderIds: Array<string | number> = addRootSelectedFolderIds): AddRootFolder[] => {
    const ids = folderIds.length > 0 ? folderIds : addRootSelectedFolderId ? [addRootSelectedFolderId] : [];
    if (ids.length === 0) return [];
    const found: AddRootFolder[] = [];
    for (const zone of addRootZones) {
      for (const endpoint of zone.endpoints) {
        for (const folder of endpoint.discoveredFolders ?? []) {
          if (ids.some((folderId) => String(folderId) === String(folder.id))) {
            found.push(folder);
          }
        }
      }
    }
    return found.filter((folder, index, rows) => rows.findIndex((candidate) => String(candidate.id) === String(folder.id)) === index);
  };

  const selectedAddRootFolder = (): AddRootFolder | null => {
    return selectedAddRootFolders()[0] ?? null;
  };

  const normalizeRootPathForParentLookup = (value: unknown): string =>
    String(value ?? '')
      .trim()
      .replace(/\\/g, '/')
      .replace(/\/+$/, '')
      .toLowerCase();

  const managedParentForFolder = (folder: AddRootFolder): StorageRootRow | null => {
    const folderEndpointId = Number(folder?.endpointId ?? 0);
    const folderPath = normalizeRootPathForParentLookup(folder?.rootPath);
    if (!Number.isFinite(folderEndpointId) || folderEndpointId <= 0 || !folderPath) return null;

    return ctxRows
      .filter((row) => Number(row?.storage_endpoint_id ?? 0) === folderEndpointId)
      .map((row) => ({
        row,
        path: normalizeRootPathForParentLookup(row?.normalized_root_path ?? row?.root_path)
      }))
      .filter(({ path }) => path && folderPath !== path && folderPath.startsWith(`${path}/`))
      .sort((a, b) => b.path.length - a.path.length)
      .map(({ row }) => row)[0] ?? null;
  };

  const managedRootKeysForAddWizard = (): string[] =>
    ctxRows.map((row) => `${Number(row?.storage_endpoint_id ?? 0)}:${normalizeRootPathForParentLookup(row?.normalized_root_path ?? row?.root_path)}`);

  async function createStorageRootFromSelection(options: { inheritGovernance?: boolean; folderIds?: Array<string | number> } = {}) {
    const selectedFolders = selectedAddRootFolders(options.folderIds ?? addRootSelectedFolderIds);
    if (selectedFolders.length === 0) {
      toast.warning('Select a discovered folder first');
      return;
    }

    addRootLoading = true;
    try {
      const createdRoots = [];
      for (const selectedFolder of selectedFolders) {
        const managedParent = managedParentForFolder(selectedFolder);
        const inheritGovernance = Boolean(managedParent) && options.inheritGovernance !== false;
        const created = await createStorageRoot(fetch, {
          storage_endpoint_id: Number(selectedFolder.endpointId),
          parent_storage_root_id: managedParent ? Number(managedParent.storage_root_id) : null,
          name: selectedFolder.folderName,
          root_path: selectedFolder.rootPath,
          inherit_owners: inheritGovernance,
          inherit_tags: inheritGovernance,
          inherit_access_profiles: inheritGovernance,
          status: 'active'
        });
        createdRoots.push(created);
      }

      toast.success(`${createdRoots.length} storage root${createdRoots.length > 1 ? 's' : ''} created`);
      detailsCache.clear();
      closeAddRootModal();
      const selectedCreatedId = createdRoots[0]?.id;
      await goto(selectedCreatedId ? `/storage-roots?selected=${selectedCreatedId}` : '/storage-roots', { replaceState: true });
      await refreshStorageRootsLoad();
    } catch {
      toast.error('Storage root operation failed');
    } finally {
      addRootLoading = false;
    }
  }

  $: if (addRootModalOpen && addRootZones.length > 0) {
    if (!addRootSelectedZoneId) {
      addRootSelectedZoneId = addRootZones[0].id;
    }
    const selectedZone = addRootZones.find((z) => String(z.id) === String(addRootSelectedZoneId));
    if (selectedZone && !addRootSelectedEndpointId) {
      addRootSelectedEndpointId = selectedZone.endpoints?.[0]?.id ?? null;
    }
  }

  $: {
    const _endpointRows = data.endpoints ?? [];
    const _discovered = discoveredFoldersByEndpointId;
    const _busy = endpointDiscoveryBusyById;
    const _state = endpointDiscoveryStateById;
    void _endpointRows;
    void _discovered;
    void _busy;
    void _state;

    rebuildAddRootZones();
  }

  /* -------------------------------------------------------------------------- */
  /* Probe + requests                                                            */
  /* -------------------------------------------------------------------------- */

  type RootProbeExecutionState = {
    status: 'idle' | 'running' | 'success' | 'failed';
    message: string | null;
    lastRunAt: string | null;
    durationMs: number | null;
    jobId?: string | null;
    reused?: boolean;
    checks?: Array<Record<string, any>>;
  };

  const emptyRootProbeExecutionState = (): RootProbeExecutionState => ({
    status: 'idle',
    message: null,
    lastRunAt: null,
    durationMs: null,
    jobId: null,
    reused: false,
    checks: []
  });

  let rootProbeBusy = false;
  let rootProbeStateByRootId: Record<number, RootProbeExecutionState> = {};

  const rootProbeState = (rootId: number | null | undefined): RootProbeExecutionState => {
    const id = Number(rootId ?? 0);
    if (!Number.isFinite(id) || id <= 0) return emptyRootProbeExecutionState();
    return rootProbeStateByRootId[id] ?? emptyRootProbeExecutionState();
  };

  const selectedProbeState = () => rootProbeState(selectedStorageRootId);

  const probeChecksFromResult = (result: any): Array<Record<string, any>> => {
    const details = result && typeof result === 'object' && !Array.isArray(result) ? result.details : null;
    const checks = details && typeof details === 'object' && Array.isArray(details.checks) ? details.checks : [];
    return checks.filter((item: any) => item && typeof item === 'object').map((item: any) => ({ ...item }));
  };

  const aclFreshnessFromOverview = (): Record<string, any> | null => {
    const freshness = (overview as any)?.acl_freshness;
    if (freshness && typeof freshness === 'object' && !Array.isArray(freshness)) {
      return freshness;
    }
    const payload = (overview as any)?.discovered_permissions_json;
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    return {
      discovered_at: payload.discovered_at ?? null,
      source: payload.source ?? null,
      probe_job_id: payload.probe_job_id ?? null,
      permissions_count: Number(payload.permissions_count ?? permissions.length ?? 0)
    };
  };

  const patchRootOverviewProbeState = (
    rootId: number,
    patch: {
      storage_endpoint_last_probe_status?: string;
      storage_endpoint_last_probe_at?: string;
      last_probe_at?: string;
      probe_last_run_at?: string;
    }
  ) => {
    if (overview && Number(overview?.storage_root_id ?? 0) === Number(rootId)) {
      setOverviewForRoot(rootId, {
        ...(overview as Record<string, unknown>),
        ...patch
      });
    }
  };

  const patchRootEndpointProbeSnapshot = (
    endpointId: number,
    patch: {
      last_probe_status: 'success' | 'failed';
      last_probe_at: string;
      last_probe_message: string;
    }
  ) => {
    const endpointRows = Array.isArray(data.endpoints) ? data.endpoints : [];
    if (endpointRows.length <= 0) return;

    data = {
      ...data,
      endpoints: endpointRows.map((ep: any) => {
        const epId = Number(ep?.storage_endpoint_id ?? ep?.id ?? 0);
        if (epId !== endpointId) return ep;
        return {
          ...ep,
          last_probe_status: patch.last_probe_status,
          last_probe_at: patch.last_probe_at,
          last_probe_message: patch.last_probe_message
        };
      })
    };
  };

  const patchRootRowProbeState = (
    targetRootId: number,
    patch: {
      status: 'success' | 'failed';
      completedAt: string;
      message: string;
    }
  ) => {
    const rows = Array.isArray(data.storageRoots) ? data.storageRoots : [];
    if (rows.length > 0) {
      data = {
        ...data,
        storageRoots: rows.map((row: any) => {
          const rowId = Number(row?.storage_root_id ?? row?.id ?? 0);
          if (rowId !== targetRootId) return row;
          return {
            ...row,
            last_probe_status: patch.status,
            last_probe_at: patch.completedAt,
            last_probe_message: patch.message,
            probe_last_status: patch.status,
            probe_last_run_at: patch.completedAt
          };
        })
      };
    }

    if (selectedRow && Number(selectedRow?.storage_root_id ?? 0) === Number(targetRootId)) {
      selectedRow = {
        ...selectedRow,
        last_probe_status: patch.status,
        last_probe_at: patch.completedAt,
        last_probe_message: patch.message,
        probe_last_status: patch.status,
        probe_last_run_at: patch.completedAt
      };
    }
  };

  const storageRootProbeMessage = (
    result: any,
    fallback: string,
    status: 'success' | 'failed'
  ): string => {
    const base = String(result?.message ?? fallback ?? '').trim() || (status === 'success' ? 'Probe completed' : 'Root probe failed');
    const failureCode = String(result?.details?.failure_code ?? '').trim();
    const rootPath = String(result?.details?.root_path ?? '').trim();
    if (status === 'success') {
      return base === 'SMB storage root reachable' ? 'Probe completed · SMB storage root reachable' : base;
    }
    let message = base;
    if (failureCode && !message.includes(failureCode)) {
      message += ` (${failureCode})`;
    }
    if (rootPath && !message.includes(rootPath)) {
      message += ` · ${rootPath}`;
    }
    return message;
  };

  const runRootProbe = async (discover: boolean) => {
    if (!selectedStorageRootId) throw new Error('No storage root selected');
    if (rootProbeBusy) throw new Error('A probe is already running');
    const rootId = selectedStorageRootId;

    const endpoint: any = selectedEndpoint();
    if (!endpoint) {
      throw new Error('Storage endpoint not found for this root');
    }

    const endpointId = Number(endpoint?.storage_endpoint_id ?? endpoint?.id ?? selectedRow?.storage_endpoint_id ?? 0);
    if (!Number.isFinite(endpointId) || endpointId <= 0) {
      throw new Error('Storage endpoint not found for this root');
    }

    rootProbeBusy = true;
    const startedAt = Date.now();
    const previousAclPermissionsCount = Number((overview as any)?.acl_freshness?.permissions_count ?? 0) || 0;
    const rootDisplayName = String(selectedRow?.storage_root_name ?? selectedRow?.name ?? `Root #${rootId}`);
    const previousProbeState = rootProbeState(rootId);
    rootProbeStateByRootId = {
      ...rootProbeStateByRootId,
      [rootId]: {
        status: 'running',
        message: discover ? 'Probe + ACL scan + discovery running' : 'Probe + ACL scan running',
        lastRunAt: previousProbeState.lastRunAt,
        durationMs: null,
        jobId: null,
        reused: false,
        checks: []
      }
    };

    try {
      const request = buildStorageRootProbeRequest({
        storageRootId: rootId,
        storageEndpointId: endpointId,
        storageRootName: String(selectedRow?.storage_root_name ?? selectedRow?.name ?? '').trim() || null,
        timeoutSec: 30,
        uiOrigin: 'admin'
      });

      const final = await runProbeWithUi({
        fetchFn: fetch,
        request,
        intervalMs: 1500,
        maxAttempts: 80,
        onUpdate: (snapshot) => {
          const checks = probeChecksFromResult(snapshot.result);
          rootProbeStateByRootId = {
            ...rootProbeStateByRootId,
            [rootId]: {
              ...rootProbeState(rootId),
              status: snapshot.status === 'running' || snapshot.status === 'queued' ? 'running' : rootProbeState(rootId).status,
              message: checks.length > 0 ? 'Probe steps received' : rootProbeState(rootId).message,
              checks
            }
          };
        },
        failureMessage: ({ errorMessage }) => errorMessage ?? 'Root probe failed'
      });

      if (!final.ok) {
        throw new Error(storageRootProbeMessage(final.result, final.errorMessage || 'Root probe failed', 'failed'));
      }

      const completedAt = new Date().toISOString();
      const successMessage = storageRootProbeMessage(final.result, 'Probe completed', 'success');
      const persistProbeResult = async (
        status: 'success' | 'failed',
        message: string
      ) => {
        try {
          await recordStorageRootProbeResult(fetch, Number(rootId), {
            last_probe_status: status,
            last_probe_at: completedAt,
            last_probe_message: message,
            source_type: 'storage_root_ui_probe'
          });
        } catch {
          // Non-blocking: local UI state remains updated even if persistence fails.
        }

        patchRootOverviewProbeState(rootId, {
          storage_endpoint_last_probe_status: status,
          storage_endpoint_last_probe_at: completedAt,
          last_probe_at: completedAt,
          probe_last_run_at: completedAt
        });

        patchRootEndpointProbeSnapshot(endpointId, {
          last_probe_status: status,
          last_probe_at: completedAt,
          last_probe_message: message
        });

        patchRootRowProbeState(rootId, {
          status,
          completedAt,
          message
        });
      };

      rootProbeStateByRootId = {
        ...rootProbeStateByRootId,
        [rootId]: {
          status: 'success',
          message: successMessage,
          lastRunAt: completedAt,
          durationMs: Date.now() - startedAt,
          jobId: final.jobId,
          checks: probeChecksFromResult(final.result)
        }
      };

      await persistProbeResult('success', successMessage);
      try {
        await createActivityEvent(fetch, {
          action: 'storage_root.probe_completed',
          outcome: 'success',
          severity: 'info',
          target_type: 'storage_root',
          target_id: rootId,
          target_display: rootDisplayName,
          root_id: rootId,
          context_json: {
            probe_status: 'success',
            probe_message: successMessage,
            job_id: final.jobId ?? null
          }
        });
      } catch {
        // best-effort activity only
      }
      prependLocalActivityRow('storage_root.probe_completed', rootId, {
        outcome: 'success',
        targetDisplay: successMessage,
        context: {
          probe_status: 'success',
          probe_message: successMessage
        }
      });

      patchRootOverviewProbeState(rootId, {
        last_probe_at: completedAt,
        probe_last_run_at: completedAt
      });

      if (discover) {
        const probeConfig = resolveStorageEndpointProbeConfig({ ...endpoint, storage_endpoint_id: endpointId });
        const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Root endpoint' });
        if (!validation.ok) {
          throw new Error(validation.message ?? 'Invalid endpoint for discovery run');
        }
        const discoveryRequest = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
          discover: true,
          timeoutSec: 30,
          uiOrigin: 'admin'
        });
        const discoveryFinal = await runProbeWithUi({
          fetchFn: fetch,
          request: discoveryRequest,
          intervalMs: 1500,
          maxAttempts: 80,
          failureMessage: ({ errorMessage }) => errorMessage ?? 'Endpoint discovery failed'
        });
        if (discoveryFinal.ok) {
          await syncStorageRootDiscoveryForEndpoint(fetch, endpointId, discoveryFinal.result);
        }
      }
      await invalidateAndReloadDetailsForRoot(rootId);
      await refreshStorageRootsLoad();
      const nextAclPermissionsCount = Number((overview as any)?.acl_freshness?.permissions_count ?? 0) || 0;
      const newAclCount = Math.max(0, nextAclPermissionsCount - previousAclPermissionsCount);
      if (newAclCount > 0) {
        try {
          await createActivityEvent(fetch, {
            action: 'storage_root.acl_discovered',
            outcome: 'success',
            severity: 'info',
            target_type: 'storage_root',
            target_id: rootId,
            target_display: rootDisplayName,
            root_id: rootId,
            context_json: {
              acl_count: nextAclPermissionsCount,
              new_acl_count: newAclCount
            }
          });
          prependLocalActivityRow('storage_root.acl_discovered', rootId, {
            outcome: 'success',
            targetDisplay: rootDisplayName,
            context: {
              acl_count: nextAclPermissionsCount,
              new_acl_count: newAclCount
            }
          });
        } catch {
          // best-effort activity only
        }
      }
      await reloadStorageRootActivity(rootId);
    } catch (e: any) {
      const completedAt = new Date().toISOString();
      const failureMessage = String(e?.message ?? 'Root probe failed');
      const persistProbeFailure = async (message: string) => {
        try {
          await recordStorageRootProbeResult(fetch, Number(rootId), {
            last_probe_status: 'failed',
            last_probe_at: completedAt,
            last_probe_message: message,
            source_type: 'storage_root_ui_probe'
          });
        } catch {
          // Non-blocking: local UI state remains updated even if persistence fails.
        }

        patchRootOverviewProbeState(rootId, {
          storage_endpoint_last_probe_status: 'failed',
          storage_endpoint_last_probe_at: completedAt,
          last_probe_at: completedAt,
          probe_last_run_at: completedAt
        });

        patchRootEndpointProbeSnapshot(endpointId, {
          last_probe_status: 'failed',
          last_probe_at: completedAt,
          last_probe_message: message
        });

        patchRootRowProbeState(rootId, {
          status: 'failed',
          completedAt,
          message
        });
      };

      rootProbeStateByRootId = {
        ...rootProbeStateByRootId,
        [rootId]: {
          status: 'failed',
          message: failureMessage,
          lastRunAt: completedAt,
          durationMs: Date.now() - startedAt,
          checks: rootProbeState(rootId).checks ?? []
        }
      };

      await persistProbeFailure(failureMessage);
      prependLocalActivityRow('storage_root.probe_failed', rootId, {
        outcome: 'failed',
        severity: 'critical',
        targetDisplay: failureMessage,
        context: {
          probe_status: 'failed',
          probe_message: failureMessage,
          storage_root_name: rootDisplayName
        }
      });

      patchRootOverviewProbeState(rootId, {
        last_probe_at: completedAt,
        probe_last_run_at: completedAt
      });
      try {
        await createActivityEvent(fetch, {
          action: 'storage_root.probe_failed',
          outcome: 'failed',
          severity: 'critical',
          target_type: 'storage_root',
          target_id: rootId,
          target_display: rootDisplayName,
          root_id: rootId,
          context_json: {
            probe_status: 'failed',
            probe_message: failureMessage,
            storage_root_name: rootDisplayName
          }
        });
      } catch {
        // best-effort activity only
      }
      await invalidateAndReloadDetailsForRoot(rootId);
      await refreshStorageRootsLoad();
      await reloadStorageRootActivity(rootId);

      throw e;
    } finally {
      rootProbeBusy = false;
    }
  };

  const runSelectedRootProbe = async () => {
    try {
      await runRootProbe(true);
      toast.success('Root probe OK: storage root is reachable');
    } catch (e: any) {
      toast.error(e?.message ?? 'Root probe failed');
    }
  };

  const openAccessRequestModal = () => {
    if (!selectedStorageRootId) {
      toast.warning('Select a storage root first');
      return;
    }
    void goto(`/access-requests?create=1&root=${encodeURIComponent(String(selectedStorageRootId))}`);
  };

  let showEffectiveAccessModal = false;
  let effectiveAccessModalLevel: 'read' | 'write' = 'read';
  function openEffectiveAccessModal(level: 'read' | 'write') {
    effectiveAccessModalLevel = level;
    showEffectiveAccessModal = true;
  }

  let showAlertsDrawer = false;
  let activityLoading = false;
  let activityRows: Array<Record<string, unknown>> = [];
  let activityLoadedForRootId: number | null = null;
  let activityRequestToken = 0;

  const activityRowsForSelectedRoot = (): Array<Record<string, unknown>> => {
    const currentRootId = Number(selectedStorageRootId ?? 0);
    if (
      currentRootId > 0 &&
      activityLoadedForRootId === currentRootId &&
      Array.isArray(activityRows)
    ) {
      return activityRows;
    }

    return [];
  };

  const recentActivityRows = (): Array<Record<string, unknown>> =>
    activityRowsForSelectedRoot().slice(0, 5);

  const prependLocalActivityRow = (
    action: string,
    rootId: number,
    payload: {
      outcome?: string;
      severity?: string;
      targetDisplay?: string | null;
      context?: Record<string, unknown>;
    } = {}
  ) => {
    activityRows = [
      {
        id: `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        action,
        outcome: payload.outcome ?? 'success',
        severity: payload.severity ?? 'info',
        target_type: 'storage_root',
        target_id: rootId,
        target_display: payload.targetDisplay ?? String(selectedRow?.storage_root_name ?? selectedRow?.name ?? `Root #${rootId}`),
        context_json: payload.context ?? {},
        created_at: new Date().toISOString()
      },
      ...activityRows.filter((entry) => Number(entry?.target_id ?? rootId) === rootId)
    ];
    activityLoadedForRootId = rootId;
  };

  async function recordStorageRootUiActivity(
    rootIdRaw: number | null | undefined,
    payload: {
      action: string;
      outcome?: string;
      severity?: string;
      message: string;
      context?: Record<string, unknown>;
    }
  ) {
    const rootId = Number(rootIdRaw ?? 0);
    if (!Number.isFinite(rootId) || rootId <= 0) return;

    prependLocalActivityRow(payload.action, rootId, {
      outcome: payload.outcome ?? 'success',
      severity: payload.severity ?? 'info',
      targetDisplay: payload.message,
      context: {
        ...(payload.context ?? {}),
        message: payload.message,
        storage_root_id: rootId,
        storage_root_name: String(selectedRow?.storage_root_name ?? selectedRow?.name ?? `Root #${rootId}`)
      }
    });

    try {
      await createActivityEvent(fetch, {
        action: payload.action,
        outcome: payload.outcome ?? 'success',
        severity: payload.severity ?? 'info',
        target_type: 'storage_root',
        target_id: rootId,
        target_display: payload.message,
        root_id: rootId,
        context_json: {
          ...(payload.context ?? {}),
          message: payload.message,
          storage_root_id: rootId,
          storage_root_name: String(selectedRow?.storage_root_name ?? selectedRow?.name ?? `Root #${rootId}`)
        }
      });
    } catch {
      // best-effort activity only
    }
  }

  async function loadStorageRootActivity(rootIdRaw: number | null | undefined) {
    const rootId = Number(rootIdRaw ?? 0);
    if (!Number.isFinite(rootId) || rootId <= 0) return;
    if (activityLoadedForRootId === rootId) return;

    const token = ++activityRequestToken;
    activityLoading = true;

    try {
      const rows = await listActivityByTarget(fetch, 'storage_root', rootId, 200);
      if (token !== activityRequestToken) return;
      activityRows = Array.isArray(rows) ? (rows as Array<Record<string, unknown>>) : [];
      activityLoadedForRootId = rootId;
    } catch {
      if (token !== activityRequestToken) return;
      activityRows = [];
      activityLoadedForRootId = rootId;
      if ($storageRootsUiStore.detailTab === 'activity') {
        toast.error('Unable to load storage root activity');
      }
    } finally {
      if (token === activityRequestToken) {
        activityLoading = false;
      }
    }
  }

  async function reloadStorageRootActivity(rootIdRaw: number | null | undefined) {
    const rootId = Number(rootIdRaw ?? 0);
    if (!Number.isFinite(rootId) || rootId <= 0) return;
    activityLoadedForRootId = null;
    await loadStorageRootActivity(rootId);
  }

  $: if (
    activityLoadedForRootId === null &&
    Number(data.storageRootActivityRootId ?? 0) > 0 &&
    Array.isArray(data.storageRootActivity)
  ) {
    activityRows = data.storageRootActivity as Array<Record<string, unknown>>;
    activityLoadedForRootId = Number(data.storageRootActivityRootId);
  }

  $: if (
    selectedStorageRootId &&
    activityLoadedForRootId !== Number(selectedStorageRootId)
  ) {
    void loadStorageRootActivity(Number(selectedStorageRootId));
  }

  function openAlertsDrawer() {
    showAlertsDrawer = true;
  }

  async function openActivityTab() {
    if (!selectedStorageRootId) {
      toast.warning('Select a storage root first');
      return;
    }

    storageRootsUiStore.setDetailTab('activity');
    await loadStorageRootActivity(Number(selectedStorageRootId));
  }

  /* -------------------------------------------------------------------------- */
  /* Tags                                                                        */
  /* -------------------------------------------------------------------------- */

  let showTagsModal = false;
  let selectedTagIds: number[] = [];
  let tagsSearch = '';
  let tagsSaving = false;
  let selectedTagIdSet = new Set<number>();
  let attachedTagIdSet = new Set<number>();
  let tagsModalWasOpen = false;
  let tagsSearchNorm = '';
  let catalogTags: UiTag[] = [];
  let availableTags: UiTag[] = [];
  let selectedTags: UiTag[] = [];

  const normalizedCatalogTags = () => normalizeTagsCatalog((data.tags ?? []) as StorageRootTagLike[]);

  const openTagsModal = () => {
    showTagsModal = true;
  };

  const attachedTagIds = (): number[] =>
    (overview?.tags ?? selectedRow?.tags ?? [])
      .map((t: any) => Number(t?.id ?? t?.tag_id ?? 0))
      .filter((id: number) => Number.isFinite(id) && id > 0);

  $: if (showTagsModal && !tagsModalWasOpen) {
    tagsModalWasOpen = true;
    selectedTagIds = attachedTagIds();
    tagsSearch = '';
  }

  $: if (!showTagsModal && tagsModalWasOpen) {
    tagsModalWasOpen = false;
  }

  $: selectedTagIdSet = new Set(selectedTagIds);
  $: tagsSearchNorm = tagsSearch.trim().toLowerCase();
  $: catalogTags = normalizedCatalogTags();
  $: attachedTagIdSet = new Set(attachedTagIds());

  $: availableTags = catalogTags
    .filter((t: any) => !selectedTagIdSet.has(Number(t.id)))
    .filter((t: any) => {
      if (!tagsSearchNorm) return true;
      const hay = [t.label, t.name, t.code]
        .map((v: any) => String(v ?? '').toLowerCase())
        .join(' ');
      return hay.includes(tagsSearchNorm);
    });

  $: selectedTags = catalogTags
    .filter((t: any) => selectedTagIdSet.has(Number(t.id)))
    .filter((t: any) => {
      if (!tagsSearchNorm) return true;
      const hay = [t.label, t.name, t.code]
        .map((v: any) => String(v ?? '').toLowerCase())
        .join(' ');
      return hay.includes(tagsSearchNorm);
    });

  function toggleTagSelection(tagId: number, checked: boolean) {
    const normalized = Number(tagId);
    if (!Number.isFinite(normalized) || normalized <= 0) return;
    const next = toggleSetValue(new Set(selectedTagIds), normalized, checked);
    selectedTagIds = [...next];
  }

  function addTagToSelection(tagId: number) {
    toggleTagSelection(tagId, true);
  }

  function removeTagFromSelection(tagId: number) {
    toggleTagSelection(tagId, false);
  }

  async function saveTags() {
    if (tagsSaving) return;
    const selectedId = selectedRow?.storage_root_id;
    if (!selectedId) {
      toast.warning('No storage root selected');
      return;
    }

    tagsSaving = true;
    try {
      const selectedIds = new Set(
        selectedTagIds
          .map((id) => Number(id))
          .filter((id) => Number.isFinite(id) && id > 0)
      );

      const tagsCatalog = (data.tags ?? []) as StorageRootTagLike[];

      const currentTags = (overview?.tags ?? selectedRow?.tags ?? []) as StorageRootTagLike[];
      const currentIds = new Set(
        currentTags
          .map((t) => tagId(t))
          .filter((id) => Number.isFinite(id) && id > 0)
      );
      const toAttachIds = [...selectedIds].filter((id) => !currentIds.has(id));
      const toDetachIds = [...currentIds].filter((id) => !selectedIds.has(id));

      if (toAttachIds.length === 0 && toDetachIds.length === 0) {
        toast.warning('No tag changes to save');
        return;
      }

      for (const toAttachId of toAttachIds) {
        await attachTagToStorageRoot(fetch, { tag_id: toAttachId, resource_id: selectedId });
      }
      for (const toDetachId of toDetachIds) {
        await detachTagFromStorageRoot(fetch, { tag_id: toDetachId, resource_id: selectedId });
      }

      const targetTags = tagsCatalog.filter((t: any) => {
        const id = tagId(t);
        return Number.isFinite(id) && selectedIds.has(id);
      });

      const normalizedTargetTags = targetTags.map((t) => ({
        ...t,
        id: tagId(t),
        label: tagLabel(t),
        name: t?.name ?? t?.label ?? '',
        color_rgb: tagColor(t)
      }));

      const updatedOverview = setOverviewForRoot(selectedId, {
        ...(overview ?? {}),
        tags: normalizedTargetTags
      });

      await refreshStorageRootsLoad();

      showTagsModal = false;
      toast.success('Tags updated');
    } catch {
      toast.error('Unable to save tag changes');
    } finally {
      tagsSaving = false;
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Governance                                                                  */
  /* -------------------------------------------------------------------------- */

  let showGovernanceDrawer = false;
  let governanceRoleTab: 'guardian' = 'guardian';
  let governanceOwners: StorageRootOwner[] = [];
  let governanceDraftGuardianIds: number[] = [];
  let governanceDraftMetadataByIdentityId: Record<number, Partial<StorageRootOwner>> = {};
  let governanceDraftDirty = false;
  let governanceUnresolvedPrincipalLabels: string[] = [];
  let governanceOwnersLoadToken = 0;
  let governanceLoading = false;
  let governanceSaving = false;
  let governanceError: string | null = null;
  let governanceOwnersLoadedForRootId: number | null = null;
  let governanceRoleRows: Array<StorageRootOwner & Record<string, any>> = [];
  let showOwnersBrowserModal = false;
  let ownersBrowserDefaultRole: 'guardian' = 'guardian';

  const GOVERNANCE_HELPER_TEXT = {
    guardian: 'Guardians manage access governance for this storage root.'
  } as const;

  const governanceEmptyTitleForRole = (role: 'guardian') => 'No guardian assigned yet';

  const governanceForRole = (role: 'guardian') =>
    governanceOwners.filter((owner) => String(owner?.role ?? '').toLowerCase() === role);

  const governancePersistedIdentityIds = (role: 'guardian') =>
    governanceForRole(role)
      .map((owner) => Number(owner?.identity_id ?? 0))
      .filter((id) => Number.isFinite(id) && id > 0)
      .filter((id, index, all) => all.indexOf(id) === index);

  const governanceDraftIdentityIds = (role: 'guardian') => governanceDraftGuardianIds;

  const governanceCurrentDraft = (): GovernanceOwnerDraft => ({
    guardianIds: normalizeOwnerIds(governanceDraftGuardianIds),
    metadataByIdentityId: governanceDraftMetadataByIdentityId ?? {}
  });

  const governanceInitialDraft = (): GovernanceOwnerDraft =>
    buildGovernanceDraftFromOwners(governanceOwners ?? []);

  const governanceHasDraftChanges = () =>
    hasGovernanceDraftChanges(governanceInitialDraft(), governanceCurrentDraft());

  const countRoleDelta = (role: 'guardian') => {
    const persisted = new Set(governancePersistedIdentityIds(role));
    const draft = new Set(governanceDraftIdentityIds(role));
    let changes = 0;
    for (const id of persisted) {
      if (!draft.has(id)) changes += 1;
    }
    for (const id of draft) {
      if (!persisted.has(id)) changes += 1;
    }
    return changes;
  };

  const governanceUnsavedChangesCount = () =>
    countRoleDelta('guardian');

  const governanceOwnersDraftForRole = (role: 'guardian'): Array<StorageRootOwner & Record<string, any>> => {
    return buildGovernanceOwnersDraftForRole(
      role,
      Number(selectedStorageRootId ?? 0),
      governanceOwners,
      governanceCurrentDraft()
    ) as Array<StorageRootOwner & Record<string, any>>;
  };

  const syncOverviewOwners = (owners: StorageRootOwner[]) => {
    if (!selectedStorageRootId) return;
    setOverviewForRoot(Number(selectedStorageRootId), {
      ...(overview ?? {}),
      owners
    });
  };

  const governanceBrowseDisabled = () =>
    governanceSaving || !selectedStorageRootId;

  const governanceOwnerTypeLabel = (owner: Record<string, any>) => {
    const value = String(owner?.identity_type ?? owner?.type ?? '').trim().toLowerCase();
    if (value.includes('group')) return 'Group';
    return 'User';
  };

  const governanceRoleRowsCount = (role: 'guardian') =>
    governanceOwnersDraftForRole(role).length;

  $: governanceRoleRows = buildGovernanceOwnersDraftForRole(
    governanceRoleTab,
    Number(selectedStorageRootId ?? 0),
    governanceOwners,
    {
      guardianIds: normalizeOwnerIds(governanceDraftGuardianIds),
      metadataByIdentityId: governanceDraftMetadataByIdentityId ?? {}
    }
  ) as Array<StorageRootOwner & Record<string, any>>;

  const resetGovernanceDraftFromOwners = () => {
    const nextDraft = buildGovernanceDraftFromOwners(governanceOwners ?? []);
    governanceDraftGuardianIds = nextDraft.guardianIds;
    governanceDraftMetadataByIdentityId = nextDraft.metadataByIdentityId;
    governanceDraftDirty = false;
  };

  const selectedRootIdentitySourceId = (): number | null => {
    const endpoint = selectedEndpoint();
    // Governance owners must resolve against the storage endpoint identity source
    // (the same one DAL validates on PUT /storage-roots/{id}/owners).
    const candidates = [
      overview?.storage_endpoint?.identity_source_id,
      endpoint?.identity_source_id,
      endpoint?.resolved_identity_source_id,
      endpoint?.effective_identity_source_id,
      endpoint?.effective_preview?.effective_identity_source_id
    ];

    for (const raw of candidates) {
      const value = Number(raw ?? 0);
      if (Number.isFinite(value) && value > 0) {
        return value;
      }
    }
    return null;
  };

  async function loadGovernanceOwners() {
    const rootId = Number(selectedStorageRootId ?? 0);
    if (!rootId) return;
    const token = ++governanceOwnersLoadToken;
    governanceLoading = true;
    governanceError = null;
    try {
      const owners = await getStorageRootOwners(fetch, rootId);
      if (token !== governanceOwnersLoadToken) return;
      governanceOwners = owners;
      syncOverviewOwners(owners);
      if (shouldResetGovernanceDraftFromOwners(governanceDraftDirty)) {
        resetGovernanceDraftFromOwners();
      }
    } catch (e: any) {
      if (token !== governanceOwnersLoadToken) return;
      governanceError = e?.message ?? 'Unable to load guardians';
      governanceOwners = Array.isArray(overview?.owners) ? overview.owners : [];
      if (shouldResetGovernanceDraftFromOwners(governanceDraftDirty)) {
        resetGovernanceDraftFromOwners();
      }
    } finally {
      if (token === governanceOwnersLoadToken) {
        governanceOwnersLoadedForRootId = rootId;
        governanceLoading = false;
      }
    }
  }

  function closeGovernanceDrawer() {
    showGovernanceDrawer = false;
    showOwnersBrowserModal = false;
    governanceError = null;
    governanceUnresolvedPrincipalLabels = [];
    resetGovernanceDraftFromOwners();
  }

  function openGovernanceDrawer(role: 'guardian' = 'guardian') {
    if (!selectedStorageRootId) {
      toast.warning('Select a storage root first');
      return;
    }
    governanceRoleTab = role;
    governanceError = null;
    governanceUnresolvedPrincipalLabels = [];
    governanceOwners = Array.isArray(overview?.owners) ? overview.owners : governanceOwners;
    governanceDraftDirty = false;
    resetGovernanceDraftFromOwners();
    showGovernanceDrawer = true;
    void loadGovernanceOwners();
  }

  async function openOwnersBrowser(role: 'guardian') {
    if (!selectedStorageRootId) {
      toast.warning('Select a storage root first');
      return;
    }
    governanceRoleTab = role;
    ownersBrowserDefaultRole = role;
    const selectedRootId = Number(selectedStorageRootId ?? 0);
    const ownersLoadedForCurrentRoot = governanceOwnersLoadedForRootId === selectedRootId;
    if (!ownersLoadedForCurrentRoot && !governanceLoading) {
      void loadGovernanceOwners();
    }
    showOwnersBrowserModal = true;
  }

  function closeOwnersBrowserModal() {
    showOwnersBrowserModal = false;
  }

  function handleGovernanceRoleTabSelect(role: 'guardian') {
    governanceRoleTab = role;
  }

  async function applyOwnersFromBrowser(event: CustomEvent<OwnersBrowserSelectionEvent>) {
    const appliedSelection = applyOwnersBrowserSelectionToDraft({
      currentDraft: governanceCurrentDraft() as unknown as {
        guardianIds: number[];
        metadataByIdentityId?: Record<number, Record<string, unknown>>;
      },
      eventDetail: (event?.detail ?? {}) as OwnersBrowserSelectionEvent,
      selectedStorageRootId
    });

    if (!appliedSelection.hasValidRootId || !appliedSelection.rootId) {
      governanceError = 'Storage root not found';
      return;
    }
    const rootId = appliedSelection.rootId;

    governanceError = null;
    const selectedGuardianIds = appliedSelection.guardianIds;
    const incomingMeta = appliedSelection.metadataByIdentityId as Record<number, Partial<StorageRootOwner>>;

    const mergedDraft = mergeBrowserSelectionIntoDraft(governanceCurrentDraft(), {
      guardianIds: selectedGuardianIds,
      metadataByIdentityId: incomingMeta
    });
    governanceDraftGuardianIds = mergedDraft.guardianIds;
    governanceDraftMetadataByIdentityId = mergedDraft.metadataByIdentityId;

    governanceRoleTab = 'guardian';

    showGovernanceDrawer = true;
    governanceUnresolvedPrincipalLabels = appliedSelection.unresolvedPrincipalLabels;
    governanceDraftDirty = governanceHasDraftChanges();
    showOwnersBrowserModal = false;

    if (governanceHasDraftChanges()) {
      await recordStorageRootUiActivity(selectedStorageRootId, {
        action: 'storage_root.guardian_selection_updated',
        outcome: 'success',
        severity: 'admin',
        message: 'Guardian selection updated. Save changes to persist.',
        context: {
          guardian_ids: governanceDraftGuardianIds,
          unresolved_principal_labels: governanceUnresolvedPrincipalLabels
        }
      });
      toast.success('Selection updated. Save changes to persist.');
    }
  }

  async function handleOwnersBrowserActivity(
    event: CustomEvent<{
      action: string;
      outcome: string;
      severity: string;
      message: string;
      context?: Record<string, unknown>;
    }>
  ) {
    const detail = event?.detail;
    if (!detail?.action || !detail?.message) return;
    await recordStorageRootUiActivity(selectedStorageRootId, {
      action: String(detail.action),
      outcome: String(detail.outcome ?? 'success'),
      severity: String(detail.severity ?? 'info'),
      message: String(detail.message),
      context: detail.context ?? {}
    });
  }

  function removeGovernanceOwner(owner: StorageRootOwner | Record<string, unknown>) {
    if (!selectedStorageRootId || governanceSaving) return;
    const identityId = Number(owner?.identity_id ?? 0);
    const role = normalizeAssignedRole(owner?.role);
    if (!Number.isFinite(identityId) || identityId <= 0) return;

    const nextDraft = removeOwnerFromDraft(governanceCurrentDraft(), {
      identityId,
      role
    });
    governanceDraftGuardianIds = nextDraft.guardianIds;
    governanceDraftMetadataByIdentityId = nextDraft.metadataByIdentityId;

    governanceDraftDirty = governanceHasDraftChanges();
  }

  async function saveGovernanceChanges() {
    if (!selectedStorageRootId || governanceSaving) return;
    if (!governanceHasDraftChanges()) {
      toast.info('No pending governance changes');
      return;
    }
    governanceSaving = true;
    governanceError = null;
    try {
      const res = await updateStorageRootOwners(fetch, Number(selectedStorageRootId), buildOwnersUpdatePayload(governanceCurrentDraft()));

      governanceOwners = Array.isArray(res?.owners) ? res.owners : [];
      syncOverviewOwners(governanceOwners);
      resetGovernanceDraftFromOwners();
      governanceUnresolvedPrincipalLabels = [];
      showOwnersBrowserModal = false;
      showGovernanceDrawer = false;
      await invalidateAndReloadDetailsForRoot(selectedStorageRootId);
      toast.success('Governance changes saved');
    } catch (e: any) {
      const rawMessage = String(e?.message ?? '').trim();
      const hasSnapshotConstraint = /active snapshot|enabled users|invalid identity ids/i.test(rawMessage);
      governanceError = hasSnapshotConstraint
        ? 'Some selected users are not eligible in the active identity snapshot. Re-open Browse directory and select enabled users from the current snapshot.'
        : rawMessage || 'Unable to update guardians';
      toast.error(governanceError);
    } finally {
      governanceSaving = false;
    }
  }

  let lastHandledStorageRootsQuery = '';
  $: if (browser && selectedStorageRootId) {
    const queryRaw = $page.url.searchParams.toString();
    const queryKey = `${Number(selectedStorageRootId)}::${queryRaw}`;
    if (queryKey !== lastHandledStorageRootsQuery) {
      lastHandledStorageRootsQuery = queryKey;

      const openGovernance = String($page.url.searchParams.get('openGovernance') ?? '').toLowerCase();
      if (openGovernance === '1' || openGovernance === 'true') {
        openGovernanceDrawer('guardian');
      }

      const openTags = String($page.url.searchParams.get('openTags') ?? '').toLowerCase();
      if (openTags === '1' || openTags === 'true') {
        openTagsModal();
      }

      const openEdit = String($page.url.searchParams.get('openEdit') ?? '').toLowerCase();
      if (openEdit === '1' || openEdit === 'true') {
        openEditRoot();
      }

      const openCreate = String($page.url.searchParams.get('create') ?? '').toLowerCase();
      if (openCreate === '1' || openCreate === 'true') {
        openCreateRoot();
      }
    }
  }
</script>

{#if !hasRoots()}
  <StorageRootEmptyState onConfigureEndpoint={() => goto('/admin/storage-endpoints')} />
{:else}
  <div class="sr-clean-layout">
    <StorageRootTreePanel
      rows={ctxRows}
      query={$storageRootsUiStore.query}
      {selectedStorageRootId}
      onSelectRoot={selectRoot}
      onCreateRoot={openCreateRoot}
      onQueryChange={(value) => storageRootsUiStore.setQuery(value)}
      onRefresh={() => {
        void refreshStorageRootsLoad();
        if (selectedStorageRootId) void invalidateAndReloadDetailsForRoot(selectedStorageRootId);
      }}
      {rootAlertSummary}
    />

    <StorageRootDetailView
      {detailsLoading}
      {selectedStorageRootId}
      selectedRootCodeOrName={String(selectedRow?.storage_root_code ?? selectedRow?.storage_root_name ?? '—').toUpperCase()}
      activeTab={$storageRootsUiStore.detailTab}
      {rootProbeBusy}
      probeState={selectedProbeState()}
      aclFreshness={aclFreshnessFromOverview()}
      alertItems={selectedRootAlerts}
      zoneLabel={selectedRow?.zone_name ?? '—'}
      endpointLabel={endpointLabel()}
      endpointAddress={endpointAddressLabel()}
      pathLabel={selectedRow?.root_path ?? '—'}
      contentSizeLabel={String((overview as any)?.estimated_size_label ?? (overview as any)?.content_size_label ?? '—')}
      contentUpdatedLabel={formatDateTimeLabel((overview as any)?.content_updated_at ?? (overview as any)?.last_content_scan_at ?? (overview as any)?.last_scan_at ?? selectedRow?.last_scan_at ?? null)}
      accessModelRows={accessModelRows()}
      projectedGroups={overview?.projected_ad_groups ?? []}
      {guardians}
      rootAvailabilityText={rootAvailabilityText()}
      rootAvailabilityTone={rootAvailabilityTone()}
      showStatusBadge={showSelectedStatusBadge()}
      lastProbeText={lastProbeLabel()}
      tags={displayTags(selectedRow)}
      effectiveAccessUsers={overview?.effective_access ?? []}
      recentActivity={recentActivityRows()}
      activityRemainder={activityRowsForSelectedRoot()}
      activityLoading={activityLoading}
      {tagId}
      {tagLabel}
      {tagColor}
      {ownerDisplayName}
      onSelectTab={selectDetailTab}
      onEditRoot={openEditRoot}
      onDeleteRoot={() => selectedRow && openDeleteRoot(selectedRow)}
      onRunRootProbe={runSelectedRootProbe}
      onNewAccessRequest={openAccessRequestModal}
      onOpenEffectiveAccess={openEffectiveAccessModal}
      onOpenGovernanceDrawer={(role) => openGovernanceDrawer(role ?? 'guardian')}
      onOpenTagsModal={openTagsModal}
      onViewAllActivity={openActivityTab}
      onViewAllAlerts={openAlertsDrawer}
    />
  </div>
{/if}

<AddStorageRootModal
  open={addRootModalOpen}
  zones={addRootZones}
  selectedZoneId={addRootSelectedZoneId}
  selectedEndpointId={addRootSelectedEndpointId}
  selectedFolderId={addRootSelectedFolderId}
  selectedFolderIds={addRootSelectedFolderIds}
  managedRootKeys={managedRootKeysForAddWizard()}
  loading={addRootLoading}
  on:close={closeAddRootModal}
  on:selectZone={(event) => handleSelectAddRootZone(event.detail.zoneId)}
  on:selectEndpoint={(event) => handleSelectAddRootEndpoint(event.detail.zoneId, event.detail.endpointId)}
  on:triggerEndpointDiscovery={(event) => handleTriggerEndpointDiscovery(event.detail.zoneId, event.detail.endpointId)}
  on:selectFolder={(event) => handleSelectAddRootFolder(event.detail.folderId)}
  on:selectFolders={(event) => handleSelectAddRootFolders(event.detail.folderIds)}
  on:create={(event) => createStorageRootFromSelection(event.detail)}
/>

<StorageRootFormModal
  open={rootModalOpen}
  mode={rootModalMode}
  root={editingRoot}
  endpoints={data.endpoints ?? []}
  onClose={() => (rootModalOpen = false)}
  onSubmit={submitRoot}
  onDelete={confirmDeleteRoot}
/>

<ConfirmDeleteDialog
  open={deleteRootModalOpen}
  onClose={() => {
    deleteRootModalOpen = false;
    editingRoot = null;
  }}
  onConfirm={confirmDeleteRoot}
  title="Delete storage root"
  description="This will remove the storage root from governance."
  impactTitle="Storage root"
  impactItems={[
    `Name: ${String(editingRoot?.display_name ?? editingRoot?.storage_root_name ?? editingRoot?.name ?? 'Storage root')}`,
    `Path: ${String(editingRoot?.root_path ?? editingRoot?.locator ?? editingRoot?.path ?? '—')}`,
    'The storage root governance record will be permanently deleted.'
  ]}
  deleteLabel="Delete"
/>

<StorageRootDrawerShell
  open={showTagsModal}
  onClose={() => (showTagsModal = false)}
  title="Manage tags"
  subtitle="Attach and detach taxonomy tags for the selected storage root."
  ariaLabelledby="sr-tags-drawer-title"
  width="560px"
  topOffset="70px"
  showFooter={true}
>
  <div class="sr-tags-modal-body">
    <p class="b2s-muted">Select the final tag set for this storage root.</p>
    <SearchField
      wrapperClass="sr-tag-search"
      placeholder="Search tags..."
      ariaLabel="Search tags"
      bind:value={tagsSearch}
    />

    <DualListPicker
      availableItems={availableTags}
      selectedItems={selectedTags}
      availableTitle="Available tags"
      selectedTitle="Assigned tags"
      getItemKey={(item) => Number(item?.id ?? 0)}
      itemLabel={(item) => String(item?.label ?? item?.name ?? item?.code ?? '-')}
      on:add={(event) => addTagToSelection(Number(event.detail.item?.id ?? 0))}
      on:remove={(event) => removeTagFromSelection(Number(event.detail.item?.id ?? 0))}
    >
      <svelte:fragment slot="item" let:item>
        <TagPill label={item.label} color={item.color_rgb ?? null} />
      </svelte:fragment>
    </DualListPicker>
  </div>

  <svelte:fragment slot="footer">
    <div class="sr-modal-actions sr-tags-modal-actions">
      <EntityActionButton compact={true} variant="secondary" label="Cancel" disabled={tagsSaving} onClick={() => (showTagsModal = false)} />
      <EntityActionButton compact={true} variant="primary" icon={tagsSaving ? 'bi-arrow-repeat' : 'bi-check2'} busy={tagsSaving} label={tagsSaving ? 'Saving…' : 'Save tag changes'} disabled={tagsSaving} onClick={saveTags} />
    </div>
  </svelte:fragment>
</StorageRootDrawerShell>

<EntityAlertDrawer
  open={showAlertsDrawer}
  onClose={() => (showAlertsDrawer = false)}
  title="Storage root alerts"
  subtitle={`Storage root · ${String(selectedRow?.storage_root_name ?? selectedRow?.storage_root_code ?? '—')}`}
  items={selectedRootAlerts}
  emptyLabel="No alert found for this storage root."
  ariaLabelledby="sr-alerts-drawer-title"
  width="640px"
  topOffset="70px"
/>

<StorageRootEffectiveAccessModal
  open={showEffectiveAccessModal}
  title={effectiveAccessModalLevel === 'write' ? 'Users with WRITE access' : 'Users with READ access'}
  contextLabel={`Storage • ${selectedRow?.zone_name ?? '—'} • ${selectedRow?.storage_root_name ?? '—'}`}
  membersCount={effectiveUsersByLevel(effectiveAccessModalLevel).length}
  level={effectiveAccessModalLevel}
  users={effectiveUsersByLevel(effectiveAccessModalLevel)}
  onAddUser={openAccessRequestModal}
  onClose={() => (showEffectiveAccessModal = false)}
/>

<StorageRootGovernanceDrawer
  open={showGovernanceDrawer}
  onClose={closeGovernanceDrawer}
  onBrowse={openOwnersBrowser}
  onSave={saveGovernanceChanges}
  onSelectRoleTab={handleGovernanceRoleTabSelect}
  onRemoveOwner={removeGovernanceOwner}
  saving={governanceSaving}
  loading={governanceLoading}
  roleTab={governanceRoleTab}
  draftDirty={governanceDraftDirty}
  selectedRootLabel={String(selectedRow?.storage_root_code ?? selectedRow?.storage_root_name ?? 'Storage root').trim().toUpperCase()}
  helperText={GOVERNANCE_HELPER_TEXT[governanceRoleTab]}
  browseDisabled={governanceBrowseDisabled()}
  errorMessage={governanceError}
  unresolvedPrincipalLabels={governanceUnresolvedPrincipalLabels}
  emptyTitle={governanceEmptyTitleForRole(governanceRoleTab)}
  roleRows={governanceRoleRows}
  canSave={governanceDraftDirty}
  unsavedChangesCount={governanceDraftDirty ? governanceUnsavedChangesCount() : 0}
  ownerDisplayName={ownerDisplayName}
  ownerTypeLabel={governanceOwnerTypeLabel}
/>

<StorageRootOwnersAdModal
  open={showOwnersBrowserModal}
  storageRootId={selectedStorageRootId}
  initialSourceId={selectedRootIdentitySourceId()}
  initialGuardianIds={governanceDraftIdentityIds('guardian')}
  defaultAssignedRole={ownersBrowserDefaultRole}
  onClose={closeOwnersBrowserModal}
  on:activity={handleOwnersBrowserActivity}
  on:save={applyOwnersFromBrowser}
/>
