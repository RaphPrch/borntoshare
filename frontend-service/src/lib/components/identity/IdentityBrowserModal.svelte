<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { onDestroy } from 'svelte';
  import TreeNode from './TreeNode.svelte';
  import SearchField from '../common/SearchField.svelte';
  import StatusBadge from '../ui/StatusBadge.svelte';
  import IdentitySelectedPrincipalRow from './IdentitySelectedPrincipalRow.svelte';
  import {
    invalidateIdentitySourceInternalCache,
    loadIdentitySourceInternalCached,
    loadIdentitySourceLastSync,
  } from '../../services/identityBrowser.api';
  import {
    bootstrapIdentityBrowser,
    loadBrowserPreviewForRow,
    loadBrowserRootTree,
    loadBrowserSubtree,
    searchBrowserDirectory
  } from './identity-browser.controller';
  import { createIdentityBrowserStore } from '../../stores/identityBrowser.store';
  import type { IdentityBrowserSource, IdentityBrowserSelectionPayload } from '../../types/identityBrowser';
  import {
    principalKey as sharedPrincipalKey,
    principalLabel,
    type PrincipalSearchItem
  } from '../../utils/principal-search';
  import { getIdentityJob, type ADImportRole, type IdentityJobStatusResponse } from '../../api/identity';
  import { runIdentitySnapshot } from '../../api/identity-sources';
  import { buildIdentitySourceProbeRequest, runProbeWithPolling } from '../../probe/probe-runner';
  import { toast } from '../../utils/toast';

  type DirectoryMode = 'single' | 'multiple';

  export let open = false;
  export let onClose: () => void = () => {};
  export let onSelect: ((payload: IdentityBrowserSelectionPayload) => void) | null = null;

  export let identitySources: IdentityBrowserSource[] = [];
  export let initialSourceId: number | null = null;

  export let title = 'Browse Active Directory';
  export let subtitle = 'Select users or groups to add to this governance role.';
  export let previewTitle = 'Preview';
  export let selectedItemsTitle = 'Selected items';
  export let roleAssignmentTitle = 'Role assignment';
  export let mode: DirectoryMode = 'multiple';
  export let allowRoleAssignment = false;
  export let allowedPrincipalType: 'all' | 'user' | 'group' | 'ou' = 'all';
  export let includeImportCandidates = true;
  export let searchLimit = 50;

  export let showImportRole = false;
  export let importRole: ADImportRole = 'user';

  export let initialSelectedKeys: string[] = [];
  export let initialRoleByKey: Record<string, { guardian?: boolean }> = {};
  export let sourceId: number | null = null;
  export let storageRootId: number | null = null;

  export let busy = false;
  export let confirmLabel = 'Use Selected';
  export let confirmBusyLabel = 'Applying…';
  export let defaultAssignedRole: 'guardian' = 'guardian';
  export let showImportButton = false;
  export let importButtonLabel = 'Import Selected';
  export let importButtonBusyLabel = 'Importing…';

  const dispatch = createEventDispatcher<{
    close: void;
    confirm: IdentityBrowserSelectionPayload;
    import: IdentityBrowserSelectionPayload;
  }>();

  const store = createIdentityBrowserStore();

  let wasOpen = false;
  let principalTypeFilter: 'all' | 'user' | 'group' | 'ou' = allowedPrincipalType;
  let expandedDns = new Set<string>();
  let loadingDns = new Set<string>();
  let selectedSourceId: number | null = null;
  let resolvedRootDn: string | null = null;
  let refreshBusy = false;
  let snapshotBusy = false;
  let lastSyncAt: string | null = null;
  let snapshotStatusLabel = 'Using latest active snapshot';
  let enabledOnlyStatusLabel = 'Filter: mixed principals (users may include disabled accounts)';

  const canRunSnapshotForSelectedSource = (): boolean => {
    const source = ($store.sources ?? []).find((row) => Number(row?.id ?? 0) === Number(selectedSourceId ?? 0));
    return Boolean(source?.canRunSnapshot);
  };

  const selectedSourceBaseDn = (sourceId: number | null = selectedSourceId): string | null => {
    const source = ($store.sources ?? []).find((row) => Number(row?.id ?? 0) === Number(sourceId ?? 0));
    return String(source?.baseDn ?? '').trim() || null;
  };

  const formatLastSync = (raw: string | null): string => {
    if (!raw) return '—';
    const dt = new Date(raw);
    if (!Number.isFinite(dt.getTime())) return '—';
    return dt.toLocaleString('en-GB');
  };

  const sourceOptionLabel = (src: any): string => {
    const name = String(src?.name ?? '').trim() || `Source #${String(src?.id ?? '')}`;
    const status = String(src?.snapshotStatus ?? '').trim().toUpperCase();
    const users = Number(src?.usersCount ?? 0) || 0;
    const groups = Number(src?.groupsCount ?? 0) || 0;
    const suffix = status ? `${status} · ${users} users · ${groups} groups` : 'No searchable snapshot';
    return `${name} · ${suffix}`;
  };

  const selectedSourceSnapshotSummary = (): string => {
    const source = ($store.sources ?? []).find((row) => Number(row?.id ?? 0) === Number(selectedSourceId ?? 0));
    if (!source) return 'No active snapshot source selected';
    if (snapshotStatusLabel !== 'Using latest active snapshot') return snapshotStatusLabel;
    const status = String(source.snapshotStatus ?? '').trim().toUpperCase() || 'UNKNOWN';
    const users = Number(source.usersCount ?? 0) || 0;
    const groups = Number(source.groupsCount ?? 0) || 0;
    const objects = Number(source.objectsCount ?? 0) || users + groups;
    return `${status} snapshot · ${users} users · ${groups} groups · ${objects} objects`;
  };

  const activeControllers = new Set<AbortController>();

  const registerController = () => {
    const controller = new AbortController();
    activeControllers.add(controller);
    return controller;
  };

  const releaseController = (controller: AbortController) => {
    activeControllers.delete(controller);
  };

  const abortAllRequests = () => {
    for (const controller of activeControllers) {
      controller.abort();
    }
    activeControllers.clear();
  };

  const addModalOpenClass = () => {
    if (typeof document === 'undefined') return;
    document.body.classList.add('modal-open');
  };

  const removeModalOpenClass = () => {
    if (typeof document === 'undefined') return;
    document.body.classList.remove('modal-open');
  };

  onDestroy(() => {
    abortAllRequests();
    removeModalOpenClass();
  });

  const principalKey = (item: PrincipalSearchItem) =>
    String(sharedPrincipalKey(item as Record<string, unknown>) ?? '').trim().toLowerCase();

  const labelForPrincipal = (item: PrincipalSearchItem | Record<string, unknown> | null | undefined): string =>
    principalLabel((item ?? {}) as Record<string, unknown>);

  const principalTypeLabel = (value: unknown): string => {
    const normalized = String(value ?? 'user').trim().toLowerCase();
    if (normalized === 'group') return 'Group';
    if (normalized === 'ou') return 'OU';
    return 'User';
  };

  const resultSecondaryInfo = (row: PrincipalSearchItem): string => {
    const login = String(row?.username ?? row?.upn ?? '').trim();
    const email = String(row?.email ?? '').trim();
    const path = String(row?.ou ?? row?.dn ?? '').trim();
    if (login && email) return `${login} · ${email}`;
    if (login) return login;
    if (email) return email;
    if (path) return path;
    return 'No additional details';
  };

  const humanizeStatus = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '—';
    return raw.replaceAll('_', ' ');
  };

  const previewImportStatus = (preview: Record<string, unknown>): string => {
    if (Boolean(preview?.is_import_candidate)) return 'Import candidate';
    if (preview?.is_import_candidate === false) return 'Imported';
    if (Boolean(preview?.is_imported)) return 'Imported';
    return '—';
  };

  const syncStatusLabel = (value: unknown): string => {
    const normalized = String(value ?? '').trim().toLowerCase();
    if (!normalized) return 'Unknown';
    if (normalized === 'up_to_date') return 'Up to date';
    if (normalized === 'needs_refresh') return 'Needs refresh';
    if (normalized === 'active') return 'Active';
    if (normalized === 'inactive') return 'Inactive';
    return humanizeStatus(normalized);
  };

  function onSourceSelectChange(event: Event) {
    const target = event.currentTarget as HTMLSelectElement | null;
    const nextId = Number(target?.value ?? 0) || null;
    void handleSourceChange(nextId, { rootDnOverride: null });
  }

  function onResultSelectionChange(row: PrincipalSearchItem, event: Event) {
    const target = event.currentTarget as HTMLInputElement | null;
    updateSelection(row, Boolean(target?.checked));
  }

  function onRoleToggle(key: string, role: 'guardian', event: Event) {
    const target = event.currentTarget as HTMLInputElement | null;
    setRole(key, role, Boolean(target?.checked));
  }

  function normalizeSelectionFromProps() {
    const keys = Array.from(new Set((initialSelectedKeys ?? []).filter(Boolean)));
    const roleByKey: Record<string, { guardian: boolean }> = {};
    for (const key of keys) {
      const existing = initialRoleByKey?.[key] ?? {};
      roleByKey[key] = {
        guardian: Boolean(existing.guardian ?? true)
      };
    }
    store.setSelectedItems(keys, {}, roleByKey);
  }

  async function initializeForOpen() {
    addModalOpenClass();
    normalizeSelectionFromProps();
    principalTypeFilter = allowedPrincipalType;

    store.setError(null);
    store.setLoading('loadingSources', true);
    try {
      const bootstrap = await bootstrapIdentityBrowser(fetch, {
        identitySources,
        initialSourceId,
        sourceId,
        storageRootId
      });
      const sources = bootstrap.sources;
      selectedSourceId = bootstrap.selectedSourceId;
      resolvedRootDn = bootstrap.resolvedRootDn;

      store.setSources(sources, selectedSourceId);

      if (!selectedSourceId) {
        store.setError("No active AD identity source available.");
        return;
      }

      await handleSourceChange(selectedSourceId, { rootDnOverride: resolvedRootDn });
    } catch (e) {
      store.setError(e?.message ?? 'Unable to load identity sources');
    } finally {
      store.setLoading('loadingSources', false);
    }
  }

  async function handleSourceChange(nextSourceId: number | null, options?: { rootDnOverride?: string | null }) {
    abortAllRequests();
    expandedDns = new Set();
    loadingDns = new Set();

    if (options?.rootDnOverride !== undefined) {
      resolvedRootDn = String(options.rootDnOverride ?? '').trim() || null;
    }

    selectedSourceId = nextSourceId;
    store.resetForSource(nextSourceId);

    if (!resolvedRootDn) {
      resolvedRootDn = selectedSourceBaseDn(nextSourceId);
    }

    snapshotStatusLabel = 'Using latest active snapshot';

    if (!nextSourceId) return;
    await loadRootTree(nextSourceId, resolvedRootDn ?? selectedSourceBaseDn(nextSourceId));
    await executeSearch(true);
    lastSyncAt = await loadIdentitySourceLastSync(fetch, nextSourceId);
  }

  async function loadRootTree(source: number, rootDnOverride?: string | null) {
    const controller = registerController();
    store.setLoading('loadingTree', true);
    try {
      const result = await loadBrowserRootTree(fetch, {
        sourceId: source,
        resolvedRootDn: rootDnOverride ?? null,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      store.setTree(result.nodes);
      const firstDn = result.firstDn;
      store.setActiveDn(firstDn);
      if (firstDn) {
        expandedDns = new Set([...expandedDns, firstDn]);
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        store.setError(e?.message ?? 'Unable to load directory tree');
      }
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) {
        store.setLoading('loadingTree', false);
      }
    }
  }

  async function toggleTreeNode(event: CustomEvent<{ dn: string; expanded: boolean }>) {
    const { dn, expanded } = event.detail;
    if (!dn || !selectedSourceId) return;

    if (!expanded) {
      const next = new Set(expandedDns);
      next.delete(dn);
      expandedDns = next;
      return;
    }

    expandedDns = new Set([...expandedDns, dn]);

    const alreadyLoading = loadingDns.has(dn);
    if (alreadyLoading) return;

    const node = findTreeNode($store.tree, dn);
    if (node?.loaded) return;

    loadingDns = new Set([...loadingDns, dn]);
    const controller = registerController();
    try {
      const children = await loadBrowserSubtree(fetch, {
        sourceId: selectedSourceId,
        dn,
        resolvedRootDn,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      store.mergeChildren(dn, children);
    } catch (e) {
      if (!controller.signal.aborted) {
        store.setError(e?.message ?? 'Unable to load sub-units');
      }
    } finally {
      releaseController(controller);
      const nextLoading = new Set(loadingDns);
      nextLoading.delete(dn);
      loadingDns = nextLoading;
    }
  }

  function findTreeNode(nodes: any[], dn: string): any {
    for (const node of nodes ?? []) {
      if (node?.dn === dn) return node;
      const fromChild = findTreeNode(node?.children ?? [], dn);
      if (fromChild) return fromChild;
    }
    return null;
  }

  function selectTreeNode(event: CustomEvent<{ dn: string }>) {
    const { dn } = event.detail;
    store.setActiveDn(dn);
    void executeSearch(true);
  }

  async function executeSearch(reset = true) {
    if (!selectedSourceId) {
      toast.warning('Select an AD source');
      return;
    }

    if (reset) {
      store.setRows([], 0);
      store.setSelectedKey(null);
      store.setPreview(null, null);
    }

    const limit = Math.max(1, Math.min(200, Math.trunc(Number(searchLimit || 50) || 50)));
    const controller = registerController();
    store.setLoading('loadingSearch', true);
    store.setError(null);
    try {
      const response = await searchBrowserDirectory(
        fetch,
        {
          selectedSourceId,
          query: String($store.query ?? '').trim(),
          activeDn: String($store.activeDn ?? '').trim() || null,
          resolvedRootDn,
          principalTypeFilter,
          searchLimit: limit,
          includeImportCandidates
        },
        controller.signal
      );
      if (controller.signal.aborted) return;
      store.setRows(response.rows, response.total);
    } catch (e) {
      if (!controller.signal.aborted) {
        store.setError(e?.message ?? 'Search failed');
      }
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) {
        store.setLoading('loadingSearch', false);
      }
    }
  }

  async function refreshDirectory() {
    if (!selectedSourceId || refreshBusy) return;
    refreshBusy = true;
    store.setError(null);
    try {
      const source: any = await loadIdentitySourceInternalCached(fetch, selectedSourceId, { force: true });
      const protocol = String(source?.protocol ?? 'ldaps').toLowerCase() === 'ldap' ? 'ldap' : 'ldaps';
      const probeRequest = buildIdentitySourceProbeRequest({
        protocol,
        host: source?.host ?? null,
        port: source?.port ?? null,
        baseDn: source?.base_dn ?? null,
        bindDn: source?.bind_dn ?? null,
        secretRef: source?.bind_password_ref ?? null,
        identitySourceId: Number(selectedSourceId)
      });

      const probe = await runProbeWithPolling({
        fetchFn: fetch,
        request: probeRequest,
        intervalMs: 2000,
        maxAttempts: 15
      });
      if (!probe.ok) {
        throw new Error(probe.errorMessage || 'Refresh probe failed');
      }

      invalidateIdentitySourceInternalCache(selectedSourceId);
      await loadRootTree(selectedSourceId, resolvedRootDn);
      await executeSearch(true);
      lastSyncAt = await loadIdentitySourceLastSync(fetch, selectedSourceId, { force: true });
      toast.success('AD tree and objects refreshed');
    } catch (e) {
      store.setError(e?.message ?? 'Unable to refresh directory');
    } finally {
      refreshBusy = false;
    }
  }

  async function regenerateSnapshot() {
    if (!selectedSourceId || snapshotBusy) return;
    if (!canRunSnapshotForSelectedSource()) return;
    snapshotBusy = true;
    store.setError(null);
    try {
      const run: any = await runIdentitySnapshot(fetch, Number(selectedSourceId), 'auto');
      const jobId = Number(run?.job_id ?? 0);
      if (!Number.isFinite(jobId) || jobId <= 0) {
        throw new Error('Snapshot job not created');
      }

      snapshotStatusLabel = 'Snapshot regeneration in progress…';

      let attempts = 0;
      const maxAttempts = 40;
      const waitMs = 1500;
      let finalState: IdentityJobStatusResponse | null = null;
      while (attempts < maxAttempts) {
        attempts += 1;
        const state = await getIdentityJob(fetch, jobId);
        const status = String(state?.status ?? '').trim().toLowerCase();
        finalState = state;

        if (status === 'success' || status === 'done' || status === 'succeeded') {
          break;
        }
        if (status === 'failed' || status === 'error') {
          const message = String((state?.error as any)?.message ?? '').trim();
          throw new Error(message || 'Snapshot regeneration failed');
        }
        await new Promise((resolve) => setTimeout(resolve, waitMs));
      }

      const terminal = String(finalState?.status ?? '').trim().toLowerCase();
      if (!(terminal === 'success' || terminal === 'done' || terminal === 'succeeded')) {
        throw new Error('Snapshot regeneration timeout');
      }

      invalidateIdentitySourceInternalCache(selectedSourceId);
      await loadRootTree(Number(selectedSourceId), resolvedRootDn);
      await executeSearch(true);
      lastSyncAt = await loadIdentitySourceLastSync(fetch, Number(selectedSourceId), { force: true });
      snapshotStatusLabel = 'Snapshot regenerated';
      toast.success('Snapshot regenerated and browser refreshed');
    } catch (e) {
      snapshotStatusLabel = 'Snapshot regeneration failed';
      store.setError(e?.message ?? 'Snapshot regeneration failed');
    } finally {
      snapshotBusy = false;
    }
  }

  function updateSelection(item: PrincipalSearchItem, checked: boolean) {
    if (!includeImportCandidates && checked && Boolean(item?.is_import_candidate)) {
      toast.warning('Import candidates are not selectable in this context');
      return;
    }

    const key = principalKey(item);
    if (!key) return;

    const selectedKeys = mode === 'single' ? [] : [...$store.selectedKeys];
    const selectedCache = { ...$store.selectedCache };
    const roleByKey = { ...$store.roleByKey };

    if (mode === 'single') {
      if (checked) {
        selectedKeys.splice(0, selectedKeys.length, key);
        for (const existingKey of Object.keys(selectedCache)) delete selectedCache[existingKey];
        selectedCache[key] = { ...item };
      } else {
        selectedKeys.splice(0, selectedKeys.length);
      }
    } else {
      const exists = selectedKeys.includes(key);
      if (checked && !exists) selectedKeys.push(key);
      if (!checked && exists) selectedKeys.splice(selectedKeys.indexOf(key), 1);

      if (checked) selectedCache[key] = { ...item };
      else delete selectedCache[key];
    }

    if (allowRoleAssignment && checked && !roleByKey[key]) {
      roleByKey[key] = {
        guardian: true
      };
    }

    if (!checked) {
      delete roleByKey[key];
    }

    store.setSelectedItems(selectedKeys, selectedCache, roleByKey);
  }

  async function selectRow(item: PrincipalSearchItem) {
    const key = principalKey(item);
    if (!key) return;
    updateSelection(item, true);
    store.setSelectedKey(key);

    const dn = String(item?.dn ?? '').trim();
    if (!dn || !selectedSourceId) {
      store.setPreview(item as Record<string, unknown>, null);
      return;
    }

    const controller = registerController();
    store.setLoading('loadingPreview', true);
    try {
      const preview = await loadBrowserPreviewForRow(fetch, {
        selectedSourceId,
        item,
        signal: controller.signal
      });
      if (controller.signal.aborted) return;
      store.setPreview((preview ?? item) as Record<string, unknown>, null);
    } catch {
      if (!controller.signal.aborted) {
        store.setPreview(item as Record<string, unknown>, null);
      }
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) {
        store.setLoading('loadingPreview', false);
      }
    }
  }

  function setRole(key: string, role: 'guardian', checked: boolean) {
    const roleByKey = { ...$store.roleByKey };
    const current = roleByKey[key] ?? { guardian: false };
    roleByKey[key] = { ...current, [role]: checked };
    store.setSelectedItems([...$store.selectedKeys], { ...$store.selectedCache }, roleByKey);
  }

  function removeSelectionByKey(key: string) {
    const selectedKeys = [...$store.selectedKeys];
    const index = selectedKeys.indexOf(key);
    if (index < 0) return;

    selectedKeys.splice(index, 1);

    const selectedCache = { ...$store.selectedCache };
    delete selectedCache[key];

    const roleByKey = { ...$store.roleByKey };
    delete roleByKey[key];

    if ($store.selectedKey === key) {
      store.setSelectedKey(selectedKeys[0] ?? null);
    }

    if (selectedKeys.length === 0) {
      store.setPreview(null, null);
    }

    store.setSelectedItems(selectedKeys, selectedCache, roleByKey);
  }

  function selectionPayload(): IdentityBrowserSelectionPayload {
    const normalizedRoles: Record<string, { guardian: boolean }> = {};
    for (const key of $store.selectedKeys) {
      const raw = $store.roleByKey[key] ?? { guardian: false };
      normalizedRoles[key] = { guardian: Boolean(raw.guardian) };
    }

    const selectedItems = $store.selectedKeys
      .map((key) => $store.selectedCache[key])
      .filter((item): item is PrincipalSearchItem => Boolean(item))
      .map((item) => ({ ...item }));

    return {
      sourceId: selectedSourceId,
      query: String($store.query ?? '').trim(),
      selectedKeys: [...$store.selectedKeys],
      selectedItems,
      roleByKey: normalizedRoles,
      importRole: importRole === 'admin' ? 'user' : importRole
    };
  }

  function closeModal() {
    abortAllRequests();
    open = false;
    removeModalOpenClass();
    dispatch('close');
    onClose();
  }

  function confirmSelection() {
    const payload = selectionPayload();
    dispatch('confirm', payload);
    onSelect?.(payload);
  }

  function importSelection() {
    if (busy || $store.loadingSearch || $store.selectedKeys.length === 0) return;
    const payload = selectionPayload();
    dispatch('import', payload);
    onSelect?.(payload);
  }

  function onEsc(event: KeyboardEvent) {
    if (!open) return;
    if (event.key !== 'Escape') return;
    event.preventDefault();
    closeModal();
  }

  function onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      closeModal();
    }
  }

  function onBackdropKeydown(event: KeyboardEvent) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (event.target !== event.currentTarget) return;
    event.preventDefault();
    closeModal();
  }

  $: {
    const activeDn = String($store.activeDn ?? '').trim();
    if (principalTypeFilter === 'user') {
      enabledOnlyStatusLabel = 'Filter: Enabled users only';
    } else if (activeDn && principalTypeFilter !== 'ou') {
      enabledOnlyStatusLabel = 'Filter: Disabled users hidden · Groups unchanged';
    } else {
      enabledOnlyStatusLabel = 'Filter: Mixed principals (users and groups)';
    }
  }

  $: if (allowedPrincipalType !== 'all' && allowedPrincipalType !== 'ou') {
    principalTypeFilter = allowedPrincipalType;
  }

  $: if (open && !wasOpen) {
    wasOpen = true;
    void initializeForOpen();
  }

  $: if (!open && wasOpen) {
    wasOpen = false;
    abortAllRequests();
    removeModalOpenClass();
  }
</script>

<svelte:window on:keydown={onEsc} />

{#if open}
  <div
    class="modal fade show d-block idb-modal"
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    on:click={onBackdropClick}
    on:keydown={onBackdropKeydown}
  >
    <div class="modal-dialog modal-xl modal-dialog-centered idb-dialog">
      <div class="modal-content rounded-4 shadow-sm border-0 idb-content">
        <div class="modal-header border-0 pb-0 idb-header">
          <div>
            <h5 class="modal-title">{title}</h5>
            <div class="small text-muted">{subtitle}</div>
          </div>
          <button type="button" class="btn-close" aria-label="Close" on:click={closeModal}></button>
        </div>

        <div class="modal-body pt-2 idb-body">
          <div class="card idb-toolbar-card">
            <div class="card-body pb-2 idb-toolbar-inner">
              <div class="row g-2 align-items-end idb-toolbar-grid">
                <div class="col-md-4 idb-source-col">
                  <label class="form-label small text-muted mb-1 idb-label" for="idb-source-select">Identity Source:</label>
                  <select
                    id="idb-source-select"
                    class="form-select form-select-sm idb-source-select"
                    bind:value={selectedSourceId}
                    disabled={$store.loadingSources || busy}
                    on:change={onSourceSelectChange}
                  >
                    {#if $store.sources.length === 0}
                      <option value={0}>No active source</option>
                    {/if}
                    {#each $store.sources as src}
                      <option value={src.id}>{sourceOptionLabel(src)}</option>
                    {/each}
                  </select>
                </div>

                <div class="col-md-5 idb-search-col">
                  <div class="form-label small text-muted mb-1 idb-label">Search users or groups</div>
                  <div class="idb-search-row">
                    <SearchField
                      wrapperClass="idb-search-field"
                      inputClass="idb-search-input"
                      placeholder="Search users or groups..."
                      ariaLabel="Search users or groups"
                      value={$store.query}
                      disabled={$store.loadingSources || busy || !selectedSourceId}
                      onChange={(next) => store.setQuery(next)}
                      onEnter={() => void executeSearch(true)}
                    />
                    <button
                      type="button"
                      class="btn btn-outline-secondary idb-search-btn"
                      aria-label="Search"
                      on:click={() => executeSearch(true)}
                      disabled={$store.loadingSearch || busy || !selectedSourceId}
                    >
                      <i class="bi bi-search"></i>
                    </button>
                  </div>
                </div>

                <div class="col-md-3 idb-role-col">
                  {#if showImportRole}
                    <label class="form-label small text-muted mb-1 idb-label" for="idb-import-role">Import role</label>
                    <select id="idb-import-role" class="form-select form-select-sm idb-role-select" bind:value={importRole}>
                      <option value="user">user</option>
                      <option value="group">group</option>
                    </select>
                  {:else}
                    <div class="idb-top-pagination">
                      <span>Last Sync: {formatLastSync(lastSyncAt)}</span>
                      <span class="idb-snapshot-status">{selectedSourceSnapshotSummary()}</span>
                    </div>
                  {/if}
                </div>

                {#if !showImportRole}
                  <div class="col-12 idb-toolbar-actions-wrap">
                    <div class="idb-toolbar-actions">
                      <button
                        type="button"
                        class="btn btn-outline-secondary btn-sm idb-toolbar-action-btn"
                        on:click={refreshDirectory}
                        disabled={busy || refreshBusy || snapshotBusy || !selectedSourceId}
                      >
                        <i class={`bi ${refreshBusy ? 'bi-arrow-repeat' : 'bi-arrow-clockwise'}`}></i>
                        {refreshBusy ? 'Refreshing…' : 'Refresh'}
                      </button>
                      <button
                        type="button"
                        class="btn btn-outline-secondary btn-sm idb-toolbar-action-btn"
                        on:click={regenerateSnapshot}
                        disabled={busy || refreshBusy || snapshotBusy || !selectedSourceId}
                        class:d-none={!canRunSnapshotForSelectedSource()}
                      >
                        <i class={`bi ${snapshotBusy ? 'bi-hourglass-split' : 'bi-database-gear'}`}></i>
                        {snapshotBusy ? 'Snapshot…' : 'Regenerate snapshot'}
                      </button>
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          </div>

          <div class="row g-0 overflow-hidden mt-3 idb-layout">
            <div class="col-3 d-flex flex-column idb-tree-panel">
              <div class="p-3 border-bottom idb-panel-head">
                <div class="d-flex align-items-center justify-content-between gap-2">
                  <div class="small text-muted text-uppercase idb-panel-title">Directory tree</div>
                </div>
              </div>
              <div class="p-2 overflow-auto idb-tree-scroll">
                {#if $store.tree.length === 0}
                  <div class="small text-muted px-2 py-1">No OU tree found for this snapshot. Search still uses the active snapshot.</div>
                {:else}
                  {#each $store.tree as node (node.dn)}
                    <TreeNode
                      {node}
                      activeDn={$store.activeDn}
                      {expandedDns}
                      {loadingDns}
                      on:toggle={toggleTreeNode}
                      on:select={selectTreeNode}
                    />
                  {/each}
                {/if}
              </div>
            </div>

            <div class="col-6 d-flex flex-column idb-results-panel">
                <div class="p-3 idb-results-head">
                  <div class="d-flex justify-content-between align-items-center mb-2 idb-results-top">
                    <div class="small text-muted idb-results-title idb-results-filter">{enabledOnlyStatusLabel}</div>
                    <div class="small text-muted idb-results-loaded">Showing {$store.rows.length} item{$store.rows.length > 1 ? 's' : ''}</div>
                  </div>
                </div>

              <div class="flex-grow-1 overflow-auto idb-table-wrap">
                <table class="table table-hover align-middle mb-0 idb-table">
                  <thead class="table-light" style="position:sticky;top:0;z-index:1;">
                    <tr>
                      <th style="width:3rem;"></th>
                      <th>Name</th>
                      <th>Details</th>
                      <th>Type</th>
                      <th>Import status</th>
                      <th>Sync status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#if $store.rows.length === 0}
                      <tr>
                        <td colspan="6" class="idb-results-empty-cell">
                          <div class="idb-results-empty">
                            <i class="bi bi-search" aria-hidden="true"></i>
                            <strong>No identities found</strong>
                            <span>Try a search, select another OU, or regenerate the snapshot.</span>
                          </div>
                        </td>
                      </tr>
                    {:else}
                      {#each $store.rows as row (principalKey(row))}
                        {@const key = principalKey(row)}
                        <tr class={$store.selectedKey === key ? 'table-active' : ''}>
                          <td>
                            <input
                              class="form-check-input"
                              type={mode === 'single' ? 'radio' : 'checkbox'}
                              checked={$store.selectedKeys.includes(key)}
                              name={mode === 'single' ? 'identity-single' : undefined}
                              disabled={busy || (!includeImportCandidates && Boolean(row?.is_import_candidate))}
                              on:change={(event) => onResultSelectionChange(row, event)}
                            />
                          </td>
                          <td>
                            <button
                              type="button"
                              class="btn btn-link btn-sm text-decoration-none p-0 idb-name-btn"
                              on:click={() => selectRow(row)}
                            >
                              <i class="bi bi-search me-2"></i>
                              {labelForPrincipal(row)}
                            </button>
                          </td>
                          <td class="small text-muted">{resultSecondaryInfo(row)}</td>
                          <td>
                            <span class={`idb-type-badge is-${String(row?.type ?? 'user').toLowerCase()}`}>
                              {principalTypeLabel(row?.type)}
                            </span>
                          </td>
                          <td class="small text-muted">
                            {#if row?.is_import_candidate}
                              <span class="idb-import-badge is-candidate"><i class="bi bi-cloud-arrow-up"></i> Import candidate</span>
                            {:else}
                              <span class="idb-import-badge is-imported"><i class="bi bi-check-circle-fill"></i> Imported</span>
                            {/if}
                          </td>
                          <td class="small text-muted">{syncStatusLabel(row?.browse_status ?? (row?.is_active ? 'active' : 'inactive'))}</td>
                        </tr>
                      {/each}
                    {/if}
                  </tbody>
                </table>
              </div>
            </div>

            <div class="col-3 d-flex flex-column idb-preview-panel">
              <div class="p-3 idb-panel-head">
                <div class="small text-muted text-uppercase idb-preview-title">{previewTitle}</div>
              </div>

              <div class="p-3 overflow-auto idb-preview-scroll">
                {#if $store.loadingPreview}
                  <div class="small text-muted">Loading preview…</div>
                {:else if !$store.preview}
                  <div class="idb-preview-empty">
                    <strong>Select a user or group</strong>
                    <span>View details and confirm before adding it to governance.</span>
                  </div>
                {:else}
                  <div class="mb-2">
                    <div class="small text-muted">Display name</div>
                    <div class="fw-semibold">{String($store.preview.display_name ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Type</div>
                    <div class="fw-semibold">{principalTypeLabel($store.preview.type)}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Username / SAM</div>
                    <div class="fw-semibold">{String($store.preview.username ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">DN</div>
                    <div class="fw-semibold text-break">{String($store.preview.dn ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">UPN</div>
                    <div class="fw-semibold">{String($store.preview.upn ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Email</div>
                    <div class="fw-semibold">{String($store.preview.email ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">OU / Path</div>
                    <div class="fw-semibold text-break">{String($store.preview.ou ?? '-')}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Import status</div>
                    <div class="fw-semibold">{previewImportStatus($store.preview)}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Sync status</div>
                    <div class="fw-semibold">{syncStatusLabel($store.preview.browse_status ?? $store.preview.status)}</div>
                  </div>
                  <div class="mb-2">
                    <div class="small text-muted">Group member count</div>
                    <div class="fw-semibold">{String($store.preview.group_count ?? $store.preview.member_count ?? '-')}</div>
                  </div>

                  {#if $store.snapshot}
                    <div class="mt-3">
                      <div class="small text-muted mb-1">Snapshot delta</div>
                      <div class="d-flex gap-2 flex-wrap">
                        <StatusBadge
                          status="success"
                          label={`+${Number($store.snapshot.added ?? 0)}`}
                          compact={true}
                        />
                        <StatusBadge
                          status="error"
                          label={`-${Number($store.snapshot.removed ?? 0)}`}
                          compact={true}
                        />
                      </div>
                    </div>
                  {/if}
                {/if}
              </div>

              {#if $store.selectedKeys.length > 0}
                <div class="p-3 idb-selected-panel">
                  <div class="small text-muted mb-2">{selectedItemsTitle}</div>
                  <div class="idb-selected-list">
                    {#each $store.selectedKeys as key}
                      {@const item = $store.selectedCache[key]}
                      <IdentitySelectedPrincipalRow
                        {item}
                        selectionKey={key}
                        onRemove={removeSelectionByKey}
                      />
                    {/each}
                  </div>
                </div>
              {/if}

              {#if allowRoleAssignment && $store.selectedKeys.length > 0}
                <div class="p-3 idb-role-panel">
                  <div class="small text-muted mb-2">{roleAssignmentTitle}</div>
                  {#each $store.selectedKeys as key}
                    <div class="small d-flex justify-content-between align-items-center mb-1">
                      <span class="text-truncate me-2">{key}</span>
                      <span class="d-flex gap-2">
                        <label class="form-check-label">
                          <input
                            class="form-check-input"
                            type="checkbox"
                            checked={$store.roleByKey[key]?.guardian === true}
                            on:change={(event) => onRoleToggle(key, 'guardian', event)}
                          />
                          G
                        </label>
                      </span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          </div>

          {#if $store.error}
            <div class="alert alert-warning mt-3 mb-0 py-2 small" role="status">{$store.error}</div>
          {/if}
        </div>

        <div class="modal-footer border-0 idb-footer">
          <div class="me-auto small text-muted">Selected: {$store.selectedKeys.length}</div>

          {#if showImportButton}
            <button
              type="button"
              class="btn btn-outline-secondary idb-btn idb-btn-secondary"
              on:click={importSelection}
              disabled={busy || $store.loadingSearch || $store.selectedKeys.length === 0}
            >
              {busy || $store.loadingSearch ? importButtonBusyLabel : `${importButtonLabel} (${$store.selectedKeys.length})`}
            </button>
          {/if}

          <button type="button" class="btn btn-outline-secondary idb-btn idb-btn-secondary" on:click={closeModal} disabled={busy}>Cancel</button>
          <button
            type="button"
            class="btn btn-primary idb-btn idb-btn-primary"
            on:click={confirmSelection}
            disabled={busy || $store.selectedKeys.length === 0}
          >
            {busy ? confirmBusyLabel : `${confirmLabel === 'Use Selected' ? 'Use Selected' : confirmLabel} (${$store.selectedKeys.length})`}
          </button>
        </div>
      </div>
    </div>
  </div>
  <div class="modal-backdrop fade show"></div>
{/if}

<style>
  .idb-modal {
    background: rgba(17, 24, 39, 0.2);
    backdrop-filter: blur(1.5px);
    z-index: 1400;
  }

  .idb-modal + .modal-backdrop {
    z-index: 1390;
  }

  .idb-dialog {
    max-width: min(1180px, 92vw);
    margin: 0.8rem auto;
  }

  .idb-content {
    border-radius: var(--b2s-card-radius, 10px);
    border: 1px solid var(--idb-border-strong, #d6deeb);
    box-shadow: var(--idb-shadow, 0 20px 40px rgba(20, 41, 72, 0.12));
    background: var(--idb-shell-bg, #ffffff);
  }

  .idb-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 0.75rem 0.85rem 0.25rem;
    border-bottom: 1px solid var(--idb-border, #e3e9f3);
    background: var(--idb-panel-head-bg, #f4f7fb);
  }

  .idb-header :global(.modal-title) {
    color: var(--idb-heading, #20324d);
  }

  .idb-header :global(.text-muted) {
    color: var(--idb-text-muted, #6b7f98) !important;
  }

  .idb-body {
    padding: 0.65rem;
    background: var(--idb-panel-soft-bg, #f7f9fc);
  }

  .idb-toolbar-card {
    background: var(--idb-panel-bg, #ffffff);
    border: 1px solid var(--idb-border, #e3e9f3);
    border-radius: var(--b2s-card-radius, 10px);
  }

  .idb-toolbar-inner {
    padding-bottom: 0.35rem;
  }

  .idb-toolbar-actions-wrap {
    margin-top: 0.25rem;
  }

  .idb-toolbar-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .idb-toolbar-action-btn {
    border-color: var(--idb-border-strong, #d6deeb);
    color: var(--idb-heading, #20324d);
    background: var(--idb-panel-bg, #ffffff);
    font-weight: 600;
  }

  .idb-toolbar-action-btn:hover {
    border-color: var(--idb-selected-border, #b8cee8);
    background: var(--idb-hover-bg, #f3f7fc);
  }

  .idb-label {
    font-size: 13px;
    font-weight: 700;
    color: var(--idb-heading, #20324d);
    text-transform: none;
  }

  .idb-source-select,
  .idb-role-select,
  .idb-search-btn {
    border-color: var(--idb-border-strong, #d6deeb);
    min-height: 36px;
    font-size: 14px;
    color: var(--idb-text, #30435f);
    background: var(--idb-panel-soft-bg, #f7f9fc);
  }

  .idb-search-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.45rem;
    align-items: center;
  }

  .idb-search-field {
    --b2s-search-border: var(--idb-border-strong, #d6deeb);
    --b2s-search-bg: var(--idb-panel-soft-bg, #f7f9fc);
    --b2s-search-color: var(--idb-text, #30435f);
    --b2s-search-icon-color: var(--idb-text-muted, #6b7f98);
    --b2s-search-placeholder: var(--idb-text-muted, #6b7f98);
    --b2s-search-focus-border: var(--idb-accent, #204c87);
    --b2s-search-focus-ring: 0 0 0 3px color-mix(in srgb, var(--idb-accent, #204c87) 18%, transparent);
    min-height: 36px;
    padding: 0.35rem 0.55rem;
    border-radius: 8px;
  }

  .idb-search-input {
    font-size: 14px;
  }

  .idb-search-btn {
    width: 40px;
    padding: 0;
    background: var(--idb-panel-head-bg, #f4f7fb);
    color: var(--idb-text-muted, #6b7f98);
  }

  .idb-top-pagination {
    min-height: 36px;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
    gap: 2px;
    color: var(--idb-heading, #20324d);
    font-weight: 600;
    font-size: 13px;
    line-height: 1;
  }

  .idb-snapshot-status {
    font-size: 11px;
    font-weight: 500;
    color: var(--idb-text-muted, #6b7f98);
  }

  .idb-layout {
    margin-top: 0.6rem;
    height: min(62vh, 640px);
    border-radius: var(--b2s-card-radius, 10px);
    border: 1px solid var(--idb-border-strong, #d6deeb);
    background: var(--idb-panel-soft-bg, #f7f9fc);
  }

  .idb-layout > .idb-tree-panel {
    flex: 0 0 24%;
    max-width: 24%;
  }

  .idb-layout > .idb-results-panel {
    flex: 0 0 48%;
    max-width: 48%;
  }

  .idb-layout > .idb-preview-panel {
    flex: 0 0 28%;
    max-width: 28%;
  }

  .idb-panel-head {
    background: var(--idb-panel-head-bg, #f4f7fb);
    border-bottom: 1px solid var(--idb-border, #e3e9f3);
    min-height: 44px;
    display: flex;
    align-items: center;
  }

  .idb-panel-title,
  .idb-results-title,
  .idb-preview-title {
    color: var(--idb-heading, #20324d);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: none;
  }

  .idb-tree-panel,
  .idb-preview-panel {
    background: var(--idb-panel-soft-bg, #f7f9fc);
  }

  .idb-results-panel {
    border-inline: 1px solid var(--idb-border, #e3e9f3);
    background: var(--idb-panel-bg, #ffffff);
  }

  .idb-tree-scroll {
    padding: 0;
  }

  .idb-results-head {
    background: var(--idb-panel-bg, #ffffff);
    border-bottom: 1px solid var(--idb-border, #e3e9f3);
    padding-bottom: 0.5rem;
  }

  .idb-results-loaded {
    font-size: 12px;
    color: var(--idb-text, #30435f);
    font-weight: 600;
  }

  .idb-table {
    font-size: 13px;
    color: var(--idb-text, #30435f);
  }

  .idb-table thead th {
    background: var(--idb-panel-head-bg, #f4f7fb);
    border-bottom: 1px solid var(--idb-border, #e3e9f3);
    color: var(--idb-text-muted, #6b7f98);
    font-weight: 700;
    font-size: 12px;
    padding: 8px 10px;
    white-space: nowrap;
  }

  .idb-table tbody td {
    border-color: var(--idb-border, #e3e9f3);
    padding: 8px 10px;
    vertical-align: middle;
    font-size: 13px;
  }

  .idb-table tbody tr.table-active,
  .idb-table tbody tr:hover {
    --bs-table-bg-state: var(--idb-selected-bg, #eaf2fb);
  }

  .idb-results-empty-cell {
    padding: 0;
  }

  .idb-results-empty {
    min-height: 210px;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 0.5rem;
    color: var(--idb-text-muted, #6b7f98);
  }

  .idb-results-empty i {
    font-size: 1.35rem;
    color: var(--idb-accent, #204c87);
    opacity: 0.8;
  }

  .idb-results-empty strong {
    color: var(--idb-heading, #20324d);
    font-size: 0.95rem;
    font-weight: 700;
  }

  .idb-results-empty span {
    max-width: 32ch;
    font-size: 0.82rem;
  }

  .idb-type-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 22px;
    border-radius: 999px;
    border: 1px solid var(--idb-border, #e3e9f3);
    padding: 0 0.55rem;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    text-transform: uppercase;
    background: var(--idb-user-badge-bg, #eef4fb);
    color: var(--idb-user-badge-text, #35557f);
  }

  .idb-type-badge.is-group {
    background: var(--idb-group-badge-bg, #f3f1fb);
    color: var(--idb-group-badge-text, #5d4b90);
  }

  .idb-type-badge.is-ou {
    background: var(--idb-panel-head-bg, #f4f7fb);
    color: var(--idb-text-muted, #6b7f98);
  }

  .idb-name-btn {
    color: var(--idb-heading, #20324d);
    font-size: 14px;
    font-weight: 700;
    line-height: 1.1;
  }

  .idb-name-btn:hover {
    color: var(--idb-heading, #20324d);
  }

  .idb-import-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-weight: 700;
    font-size: 12px;
    line-height: 1;
  }

  .idb-import-badge.is-imported {
    color: var(--idb-success, #2d7f4f);
  }

  .idb-import-badge.is-candidate {
    color: var(--idb-warning, #c1761f);
  }

  .idb-results-filter {
    font-size: 12px;
    font-weight: 600;
    color: var(--idb-text-muted, #6b7f98);
  }

  .idb-preview-scroll {
    color: var(--idb-text, #30435f);
    font-size: 13px;
    background: var(--idb-panel-soft-bg, #f7f9fc);
  }

  .idb-preview-empty {
    min-height: 180px;
    padding: 0.6rem;
    border: 1px dashed var(--idb-border-strong, #d6deeb);
    border-radius: 12px;
    background: var(--idb-panel-bg, #ffffff);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.4rem;
  }

  .idb-preview-empty strong {
    color: var(--idb-heading, #20324d);
    font-size: 0.95rem;
    font-weight: 700;
  }

  .idb-preview-empty span {
    color: var(--idb-text-muted, #6b7f98);
    font-size: 0.82rem;
    line-height: 1.35;
  }

  .idb-preview-scroll .small.text-muted {
    color: var(--idb-text-muted, #6b7f98);
    font-size: 12px;
    text-transform: none;
    letter-spacing: 0;
  }

  .idb-preview-scroll .fw-semibold {
    font-size: 16px;
    color: var(--idb-heading, #20324d);
    font-weight: 700;
    line-height: 1.15;
  }

  .idb-selected-panel {
    max-height: 220px;
    overflow: auto;
    border-top: 1px solid var(--idb-border, #e3e9f3);
    background: var(--idb-panel-head-bg, #f4f7fb);
  }

  .idb-role-panel {
    border-top: 1px solid var(--idb-border, #e3e9f3);
    background: var(--idb-panel-head-bg, #f4f7fb);
  }

  .idb-selected-list {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .idb-footer {
    border-top: 1px solid var(--idb-border, #e3e9f3);
    background: var(--idb-panel-head-bg, #f4f7fb);
    padding: 0.65rem 0.85rem;
    gap: 0.4rem;
  }

  .idb-btn {
    min-height: 36px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    padding: 0.35rem 0.85rem;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
  }

  .idb-btn-secondary {
    border-color: var(--idb-border-strong, #d6deeb);
    color: var(--idb-heading, #20324d);
    background: var(--idb-panel-bg, #ffffff);
  }

  .idb-btn-secondary:hover {
    background: var(--idb-hover-bg, #f3f7fc);
    border-color: var(--idb-selected-border, #b8cee8);
  }

  .idb-btn-primary {
    border-color: var(--idb-accent, #204c87);
    background: var(--idb-accent, #204c87);
    color: #ffffff;
  }

  .idb-btn-primary:hover {
    background: color-mix(in srgb, var(--idb-accent, #204c87) 88%, black 12%);
    border-color: color-mix(in srgb, var(--idb-accent, #204c87) 88%, black 12%);
  }

  .idb-role-panel :global(.form-check-input:checked) {
    background-color: var(--idb-accent, #204c87);
    border-color: var(--idb-accent, #204c87);
  }

  @media (max-width: 1180px) {
    .idb-layout {
      height: auto;
      min-height: 56vh;
    }

    .idb-layout > .idb-tree-panel {
      flex: 0 0 28%;
      max-width: 28%;
    }

    .idb-layout > .idb-results-panel {
      flex: 0 0 44%;
      max-width: 44%;
    }

    .idb-layout > .idb-preview-panel {
      flex: 0 0 28%;
      max-width: 28%;
    }
  }

  @media (max-width: 920px) {
    .idb-dialog {
      max-width: min(1180px, 96vw);
    }

    .idb-layout {
      display: flex;
      flex-direction: column;
      max-height: none;
      height: auto;
    }

    .idb-layout > .idb-tree-panel,
    .idb-layout > .idb-results-panel,
    .idb-layout > .idb-preview-panel {
      max-width: 100%;
      flex: 1 1 auto;
      border-inline: 0;
    }

    .idb-layout > .idb-results-panel {
      border-top: 1px solid var(--idb-border, #e3e9f3);
      border-bottom: 1px solid var(--idb-border, #e3e9f3);
    }

    .idb-toolbar-actions {
      justify-content: flex-start;
    }
  }
</style>
