<script lang="ts">
  import { t, intlLocale } from '$lib/i18n';
  import { createEventDispatcher } from 'svelte';
  import { onDestroy } from 'svelte';
  import TreeNode from './TreeNode.svelte';
  import SearchField from '../ui/SearchField.svelte';
  import StatusBadge from '../ui/StatusBadge.svelte';
  import AppModal from '../ui/AppModal.svelte';
  import IdentitySelectedPrincipalRow from './IdentitySelectedPrincipalRow.svelte';
  import {
    invalidateIdentitySourceInternalCache,
    loadIdentitySourceInternalCached,
    loadIdentitySourceLastSync,
  } from '../../api/identity-browser';
  import {
    bootstrapIdentityBrowser,
    loadBrowserPreviewForRow,
    loadBrowserRootTree,
    loadBrowserSubtree,
    searchBrowserDirectory
  } from './identity-browser.controller';
  import { createIdentityBrowserStore } from '../../stores/identity-browser.store';
  import type { IdentityBrowserSource, IdentityBrowserSelectionPayload } from '../../types/identity-browser';
  import {
    principalKey as sharedPrincipalKey,
    principalLabel,
    type PrincipalSearchItem
  } from '../../utils/principal-search';
  import { getIdentityJob, type ADImportRole, type IdentityJobStatusResponse } from '../../api/identity';
  import { runIdentitySnapshot } from '../../api/identity-sources';
  import { buildIdentitySourceProbeRequest, runProbeWithPolling } from '../../jobs/probe-runner';
  import { toast } from '../../stores/toast';

  type DirectoryMode = 'single' | 'multiple';

  export let open = false;
  export let onClose: () => void = () => {};
  export let onSelect: ((payload: IdentityBrowserSelectionPayload) => void) | null = null;

  export let identitySources: IdentityBrowserSource[] = [];
  export let initialSourceId: number | null = null;

  export let title = t('Browse Active Directory');
  export let subtitle = t('Select users or groups to add to this governance role.');
  export let previewTitle = t('Preview');
  export let selectedItemsTitle = t('Selected items');
  export let roleAssignmentTitle = t('Role assignment');
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
  export let confirmLabel = t('Use Selected');
  export let confirmBusyLabel = t('Applying…');
  export let defaultAssignedRole: 'guardian' = 'guardian';
  export let showImportButton = false;
  export let importButtonLabel = t('Import Selected');
  export let importButtonBusyLabel = t('Importing…');

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
  let snapshotStatusLabel = t('Using latest active snapshot');
  let enabledOnlyStatusLabel = t('Filter: mixed principals (users may include disabled accounts)');

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
    return dt.toLocaleString(intlLocale());
  };

  const sourceOptionLabel = (src: any): string => {
    const name = String(src?.name ?? '').trim() || t('Source #{String}', { String: String(src?.id ?? '') });
    const status = String(src?.snapshotStatus ?? '').trim().toUpperCase();
    const users = Number(src?.usersCount ?? 0) || 0;
    const groups = Number(src?.groupsCount ?? 0) || 0;
    const suffix = status ? t('{status} · {users} users · {groups} groups', { status, users, groups }) : t('No searchable snapshot');
    return `${name} · ${suffix}`;
  };

  const selectedSourceSnapshotSummary = (): string => {
    const source = ($store.sources ?? []).find((row) => Number(row?.id ?? 0) === Number(selectedSourceId ?? 0));
    if (!source) return t('No active snapshot source selected');
    if (snapshotStatusLabel !== t('Using latest active snapshot')) return snapshotStatusLabel;
    const status = String(source.snapshotStatus ?? '').trim().toUpperCase() || 'UNKNOWN';
    const users = Number(source.usersCount ?? 0) || 0;
    const groups = Number(source.groupsCount ?? 0) || 0;
    const objects = Number(source.objectsCount ?? 0) || users + groups;
    return t('{status} snapshot · {users} users · {groups} groups · {objects} objects', { status, users, groups, objects });
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
    if (normalized === 'group') return t('Group');
    if (normalized === 'ou') return 'OU';
    return t('User');
  };

  const resultSecondaryInfo = (row: PrincipalSearchItem): string => {
    const login = String(row?.username ?? row?.upn ?? '').trim();
    const email = String(row?.email ?? '').trim();
    const path = String(row?.ou ?? row?.dn ?? '').trim();
    if (login && email) return `${login} · ${email}`;
    if (login) return login;
    if (email) return email;
    if (path) return path;
    return t('No additional details');
  };

  const humanizeStatus = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '—';
    return raw.replaceAll('_', ' ');
  };

  const previewImportStatus = (preview: Record<string, unknown>): string => {
    if (Boolean(preview?.is_import_candidate)) return t('Import candidate');
    if (preview?.is_import_candidate === false) return t('Imported');
    if (Boolean(preview?.is_imported)) return t('Imported');
    return '—';
  };

  const syncStatusLabel = (value: unknown): string => {
    const normalized = String(value ?? '').trim().toLowerCase();
    if (!normalized) return t('Unknown');
    if (normalized === 'up_to_date') return t('Up to date');
    if (normalized === 'needs_refresh') return t('Needs refresh');
    if (normalized === 'active') return t('Active');
    if (normalized === 'inactive') return t('Inactive');
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
      store.setError(e?.message ?? t('Unable to load identity sources'));
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

    snapshotStatusLabel = t('Using latest active snapshot');

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
        store.setError(e?.message ?? t('Unable to load directory tree'));
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
        store.setError(e?.message ?? t('Unable to load sub-units'));
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
      toast.warning(t('Select an AD source'));
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
        store.setError(e?.message ?? t('Search failed'));
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
        throw new Error(probe.errorMessage || t('Refresh probe failed'));
      }

      invalidateIdentitySourceInternalCache(selectedSourceId);
      await loadRootTree(selectedSourceId, resolvedRootDn);
      await executeSearch(true);
      lastSyncAt = await loadIdentitySourceLastSync(fetch, selectedSourceId, { force: true });
      toast.success(t('AD tree and objects refreshed'));
    } catch (e) {
      store.setError(e?.message ?? t('Unable to refresh directory'));
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

      snapshotStatusLabel = t('Snapshot regeneration in progress…');

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
          throw new Error(message || t('Snapshot regeneration failed'));
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
      snapshotStatusLabel = t('Snapshot regenerated');
      toast.success(t('Snapshot regenerated and browser refreshed'));
    } catch (e) {
      snapshotStatusLabel = t('Snapshot regeneration failed');
      store.setError(e?.message ?? t('Snapshot regeneration failed'));
    } finally {
      snapshotBusy = false;
    }
  }

  function updateSelection(item: PrincipalSearchItem, checked: boolean) {
    if (!includeImportCandidates && checked && Boolean(item?.is_import_candidate)) {
      toast.warning(t('Import candidates are not selectable in this context'));
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




  $: {
    const activeDn = String($store.activeDn ?? '').trim();
    if (principalTypeFilter === 'user') {
      enabledOnlyStatusLabel = t('Filter: Enabled users only');
    } else if (activeDn && principalTypeFilter !== 'ou') {
      enabledOnlyStatusLabel = t('Filter: Disabled users hidden · Groups unchanged');
    } else {
      enabledOnlyStatusLabel = t('Filter: Mixed principals (users and groups)');
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

<AppModal
  {open}
  onClose={closeModal}
  backdropClass="b2s-modal-backdrop idb-backdrop"
  modalClass="b2s-modal idb-dialog"
  contentClass="idb-content"
  ariaLabelledby="idb-title"
  showClose={false}
  useFly={false}
>
  <header class="idb-header">
    <div>
      <h2 id="idb-title" class="idb-title">{title}</h2>
      <div class="idb-subtitle">{subtitle}</div>
    </div>
    <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm b2s-btn-icon" aria-label={t('Close')} on:click={closeModal}>
      <i class="bi bi-x-lg" aria-hidden="true"></i>
    </button>
  </header>

  <div class="idb-body">
    <div class="idb-toolbar-card">
      <div class="idb-toolbar-grid">
        <div>
          <label class="idb-label" for="idb-source-select">{t('Identity Source:')}</label>
          <select
            id="idb-source-select"
            class="idb-select"
            bind:value={selectedSourceId}
            disabled={$store.loadingSources || busy}
            on:change={onSourceSelectChange}
          >
            {#if $store.sources.length === 0}
              <option value={0}>{t('No active source')}</option>
            {/if}
            {#each $store.sources as src}
              <option value={src.id}>{sourceOptionLabel(src)}</option>
            {/each}
          </select>
        </div>

        <div>
          <div class="idb-label">{t('Search users or groups')}</div>
          <div class="idb-search-row">
            <SearchField
              wrapperClass="idb-search-field"
              inputClass="idb-search-input"
              placeholder={t('Search users or groups...')}
              ariaLabel={t('Search users or groups')}
              value={$store.query}
              disabled={$store.loadingSources || busy || !selectedSourceId}
              onChange={(next) => store.setQuery(next)}
              onEnter={() => void executeSearch(true)}
            />
            <button
              type="button"
              class="b2s-btn b2s-btn-secondary b2s-btn-icon idb-search-btn"
              aria-label={t('Search')}
              on:click={() => executeSearch(true)}
              disabled={$store.loadingSearch || busy || !selectedSourceId}
            >
              <i class="bi bi-search"></i>
            </button>
          </div>
        </div>

        <div>
          {#if showImportRole}
            <label class="idb-label" for="idb-import-role">{t('Import role')}</label>
            <select id="idb-import-role" class="idb-select" bind:value={importRole}>
              <option value="user">user</option>
              <option value="group">group</option>
            </select>
          {:else}
            <div class="idb-top-pagination">
              <span>{t('Last Sync: {formatLastSync}', { formatLastSync: formatLastSync(lastSyncAt) })}</span>
              <span class="idb-snapshot-status">{selectedSourceSnapshotSummary()}</span>
            </div>
          {/if}
        </div>

        {#if !showImportRole}
          <div class="idb-toolbar-actions">
            <button
              type="button"
              class="b2s-btn b2s-btn-secondary b2s-btn-sm"
              on:click={refreshDirectory}
              disabled={busy || refreshBusy || snapshotBusy || !selectedSourceId}
            >
              <i class={`bi ${refreshBusy ? 'bi-arrow-repeat' : 'bi-arrow-clockwise'}`}></i>
              {refreshBusy ? t('Refreshing…') : t('Refresh')}
            </button>
            {#if canRunSnapshotForSelectedSource()}
              <button
                type="button"
                class="b2s-btn b2s-btn-secondary b2s-btn-sm"
                on:click={regenerateSnapshot}
                disabled={busy || refreshBusy || snapshotBusy || !selectedSourceId}
              >
                <i class={`bi ${snapshotBusy ? 'bi-hourglass-split' : 'bi-database-gear'}`}></i>
                {snapshotBusy ? t('Snapshot…') : t('Regenerate snapshot')}
              </button>
            {/if}
          </div>
        {/if}
      </div>
    </div>

    <div class="idb-layout">
      <section class="idb-panel idb-tree-panel">
        <div class="idb-panel-head">
          <div class="idb-panel-title">{t('Directory tree')}</div>
        </div>
        <div class="idb-scroll idb-tree-scroll">
          {#if $store.tree.length === 0}
            <div class="idb-hint">{t('No OU tree found for this snapshot. Search still uses the active snapshot.')}</div>
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
      </section>

      <section class="idb-panel idb-results-panel">
        <div class="idb-results-head">
          <div class="idb-results-filter">{enabledOnlyStatusLabel}</div>
          <div class="idb-results-loaded">{t('Showing {rowsCount} item{value}', { rowsCount: $store.rows.length, value: ($store.rows.length > 1 ? 's' : '') })}</div>
        </div>

        <div class="idb-scroll">
          <table class="idb-table">
            <thead>
              <tr>
                <th style="width:3rem;"></th>
                <th>{t('Name')}</th>
                <th>{t('Details')}</th>
                <th>{t('Type')}</th>
                <th>{t('Import status')}</th>
                <th>{t('Sync status')}</th>
              </tr>
            </thead>
            <tbody>
              {#if $store.rows.length === 0}
                <tr>
                  <td colspan="6" class="idb-results-empty-cell">
                    <div class="idb-results-empty">
                      <i class="bi bi-search" aria-hidden="true"></i>
                      <strong>{t('No identities found')}</strong>
                      <span>{t('Try a search, select another OU, or regenerate the snapshot.')}</span>
                    </div>
                  </td>
                </tr>
              {:else}
                {#each $store.rows as row (principalKey(row))}
                  {@const key = principalKey(row)}
                  <tr class:is-selected={$store.selectedKey === key}>
                    <td>
                      <input
                        type={mode === 'single' ? 'radio' : 'checkbox'}
                        checked={$store.selectedKeys.includes(key)}
                        name={mode === 'single' ? 'identity-single' : undefined}
                        disabled={busy || (!includeImportCandidates && Boolean(row?.is_import_candidate))}
                        on:change={(event) => onResultSelectionChange(row, event)}
                      />
                    </td>
                    <td>
                      <button type="button" class="idb-name-btn" on:click={() => selectRow(row)}>
                        <i class="bi bi-search"></i>
                        {labelForPrincipal(row)}
                      </button>
                    </td>
                    <td class="idb-muted">{resultSecondaryInfo(row)}</td>
                    <td>
                      <span class={`idb-type-badge is-${String(row?.type ?? 'user').toLowerCase()}`}>
                        {principalTypeLabel(row?.type)}
                      </span>
                    </td>
                    <td>
                      {#if row?.is_import_candidate}
                        <span class="idb-import-badge is-candidate"><i class="bi bi-cloud-arrow-up"></i> {t('Import candidate')}</span>
                      {:else}
                        <span class="idb-import-badge is-imported"><i class="bi bi-check-circle-fill"></i> {t('Imported')}</span>
                      {/if}
                    </td>
                    <td class="idb-muted">{syncStatusLabel(row?.browse_status ?? (row?.is_active ? 'active' : 'inactive'))}</td>
                  </tr>
                {/each}
              {/if}
            </tbody>
          </table>
        </div>
      </section>

      <section class="idb-panel idb-preview-panel">
        <div class="idb-panel-head">
          <div class="idb-panel-title">{previewTitle}</div>
        </div>

        <div class="idb-scroll idb-preview-scroll">
          {#if $store.loadingPreview}
            <div class="idb-hint">{t('Loading preview…')}</div>
          {:else if !$store.preview}
            <div class="idb-preview-empty">
              <strong>{t('Select a user or group')}</strong>
              <span>{t('View details and confirm before adding it to governance.')}</span>
            </div>
          {:else}
            {@const p = $store.preview}
            <dl class="idb-preview-fields">
              {#each [
                ['Display name', String(p.display_name ?? '-')],
                ['Type', principalTypeLabel(p.type)],
                ['Username / SAM', String(p.username ?? '-')],
                ['DN', String(p.dn ?? '-')],
                ['UPN', String(p.upn ?? '-')],
                ['Email', String(p.email ?? '-')],
                ['OU / Path', String(p.ou ?? '-')],
                ['Import status', previewImportStatus(p)],
                ['Sync status', syncStatusLabel(p.browse_status ?? p.status)],
                ['Group member count', String(p.group_count ?? p.member_count ?? '-')]
              ] as [label, value]}
                <div>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              {/each}
            </dl>

            {#if $store.snapshot}
              <div class="idb-snapshot-delta">
                <div class="idb-hint">{t('Snapshot delta')}</div>
                <div class="idb-badges">
                  <StatusBadge status="success" label={`+${Number($store.snapshot.added ?? 0)}`} compact={true} />
                  <StatusBadge status="error" label={`-${Number($store.snapshot.removed ?? 0)}`} compact={true} />
                </div>
              </div>
            {/if}
          {/if}
        </div>

        {#if $store.selectedKeys.length > 0}
          <div class="idb-selected-panel">
            <div class="idb-hint">{selectedItemsTitle}</div>
            <div class="idb-selected-list">
              {#each $store.selectedKeys as key}
                {@const item = $store.selectedCache[key]}
                <IdentitySelectedPrincipalRow {item} selectionKey={key} onRemove={removeSelectionByKey} />
              {/each}
            </div>
          </div>
        {/if}

        {#if allowRoleAssignment && $store.selectedKeys.length > 0}
          <div class="idb-role-panel">
            <div class="idb-hint">{roleAssignmentTitle}</div>
            {#each $store.selectedKeys as key}
              <div class="idb-role-row">
                <span class="idb-role-key">{key}</span>
                <label>
                  <input
                    type="checkbox"
                    checked={$store.roleByKey[key]?.guardian === true}
                    on:change={(event) => onRoleToggle(key, 'guardian', event)}
                  />
                  G
                </label>
              </div>
            {/each}
          </div>
        {/if}
      </section>
    </div>

    {#if $store.error}
      <div class="idb-error" role="status">{$store.error}</div>
    {/if}
  </div>

  <footer class="idb-footer">
    <div class="idb-hint idb-footer-count">{t('Selected: {selectedKeysCount}', { selectedKeysCount: $store.selectedKeys.length })}</div>

    {#if showImportButton}
      <button
        type="button"
        class="b2s-btn b2s-btn-secondary"
        on:click={importSelection}
        disabled={busy || $store.loadingSearch || $store.selectedKeys.length === 0}
      >
        {busy || $store.loadingSearch ? importButtonBusyLabel : `${importButtonLabel} (${$store.selectedKeys.length})`}
      </button>
    {/if}

    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={closeModal} disabled={busy}>{t('Cancel')}</button>
    <button
      type="button"
      class="b2s-btn b2s-btn-primary"
      on:click={confirmSelection}
      disabled={busy || $store.selectedKeys.length === 0}
    >
      {busy ? confirmBusyLabel : `${confirmLabel} (${$store.selectedKeys.length})`}
    </button>
  </footer>
</AppModal>

<style>
  :global(.b2s-modal-backdrop.idb-backdrop) {
    z-index: 1400;
    background: rgba(17, 24, 39, 0.2);
    backdrop-filter: blur(1.5px);
  }

  :global(.b2s-modal.idb-dialog) {
    position: relative;
    top: auto;
    left: auto;
    transform: none;
    width: min(1180px, 92vw);
    max-height: calc(100vh - 32px);
    border: 1px solid var(--idb-border-strong);
    border-radius: var(--b2s-card-radius);
    box-shadow: var(--idb-shadow);
    background: var(--idb-shell-bg);
    overflow: hidden;
  }

  :global(.idb-content) {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .idb-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px 8px;
    border-bottom: 1px solid var(--idb-border);
    background: var(--idb-panel-head-bg);
  }

  .idb-title {
    margin: 0;
    font-size: var(--b2s-fs-xl);
    font-weight: 500;
    color: var(--idb-heading);
  }

  .idb-subtitle,
  .idb-hint,
  .idb-muted {
    font-size: var(--b2s-fs-sm);
    color: var(--idb-text-muted);
  }

  .idb-body {
    padding: 10px;
    overflow: auto;
    background: var(--idb-panel-soft-bg);
  }

  .idb-toolbar-card {
    padding: 14px 16px 10px;
    background: var(--idb-panel-bg);
    border: 1px solid var(--idb-border);
    border-radius: var(--b2s-card-radius);
  }

  .idb-toolbar-grid {
    display: grid;
    grid-template-columns: 4fr 5fr 3fr;
    gap: 8px;
    align-items: end;
  }

  .idb-toolbar-actions {
    grid-column: 1 / -1;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    flex-wrap: wrap;
  }

  .idb-label {
    display: block;
    margin-bottom: 4px;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    color: var(--idb-heading);
  }

  .idb-select {
    width: 100%;
    min-height: 36px;
    padding: 4px 8px;
    border: 1px solid var(--idb-border-strong);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-md);
    color: var(--idb-text);
    background: var(--idb-panel-soft-bg);
  }

  .idb-search-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 7px;
    align-items: center;
  }

  :global(.idb-search-field) {
    --b2s-search-border: var(--idb-border-strong);
    --b2s-search-bg: var(--idb-panel-soft-bg);
    --b2s-search-color: var(--idb-text);
    --b2s-search-icon-color: var(--idb-text-muted);
    --b2s-search-placeholder: var(--idb-text-muted);
    --b2s-search-focus-border: var(--idb-accent);
    --b2s-search-focus-ring: 0 0 0 3px color-mix(in srgb, var(--idb-accent) 18%, transparent);
    min-height: 36px;
    padding: 6px 9px;
    border-radius: var(--b2s-radius-sm);
  }

  :global(.idb-search-input) {
    font-size: var(--b2s-fs-md);
  }

  .idb-search-btn {
    min-height: 36px;
    height: 36px;
  }

  .idb-top-pagination {
    min-height: 36px;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
    gap: 2px;
    color: var(--idb-heading);
    font-weight: 600;
    font-size: var(--b2s-fs-sm);
    line-height: 1;
  }

  .idb-snapshot-status {
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
    color: var(--idb-text-muted);
  }

  .idb-layout {
    display: grid;
    grid-template-columns: 24% 48% 28%;
    margin-top: 10px;
    height: min(62vh, 640px);
    overflow: hidden;
    border-radius: var(--b2s-card-radius);
    border: 1px solid var(--idb-border-strong);
    background: var(--idb-panel-soft-bg);
  }

  .idb-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
  }

  .idb-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
  }

  .idb-panel-head {
    display: flex;
    align-items: center;
    min-height: 44px;
    padding: 0 16px;
    background: var(--idb-panel-head-bg);
    border-bottom: 1px solid var(--idb-border);
  }

  .idb-panel-title {
    color: var(--idb-heading);
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
  }

  .idb-tree-panel .idb-hint {
    padding: 8px 12px;
  }

  .idb-results-panel {
    border-inline: 1px solid var(--idb-border);
    background: var(--idb-panel-bg);
  }

  .idb-results-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding: 16px 16px 8px;
    border-bottom: 1px solid var(--idb-border);
  }

  .idb-results-filter {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--idb-text-muted);
  }

  .idb-results-loaded {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--idb-text);
  }

  .idb-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--b2s-fs-sm);
    color: var(--idb-text);
  }

  .idb-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 8px 10px;
    text-align: left;
    white-space: nowrap;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
    color: var(--idb-text-muted);
    background: var(--idb-panel-head-bg);
    border-bottom: 1px solid var(--idb-border);
  }

  .idb-table tbody td {
    padding: 8px 10px;
    vertical-align: middle;
    border-bottom: 1px solid var(--idb-border);
  }

  .idb-table tbody tr:hover,
  .idb-table tbody tr.is-selected {
    background: var(--idb-selected-bg);
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
    gap: 8px;
    color: var(--idb-text-muted);
  }

  .idb-results-empty i {
    font-size: 1.35rem;
    color: var(--idb-accent);
    opacity: 0.8;
  }

  .idb-results-empty strong,
  .idb-preview-empty strong {
    color: var(--idb-heading);
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .idb-results-empty span {
    max-width: 32ch;
    font-size: var(--b2s-fs-sm);
  }

  .idb-type-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 22px;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid var(--idb-border);
    padding: 0 9px;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
    letter-spacing: 0.01em;
    text-transform: uppercase;
    background: var(--idb-user-badge-bg);
    color: var(--idb-user-badge-text);
  }

  .idb-type-badge.is-group {
    background: var(--idb-group-badge-bg);
    color: var(--idb-group-badge-text);
  }

  .idb-type-badge.is-ou {
    background: var(--idb-panel-head-bg);
    color: var(--idb-text-muted);
  }

  .idb-name-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0;
    border: 0;
    background: none;
    cursor: pointer;
    color: var(--idb-heading);
    font-size: var(--b2s-fs-md);
    font-weight: 700;
    line-height: 1.1;
    text-align: left;
  }

  .idb-import-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-weight: 700;
    font-size: var(--b2s-fs-xs);
    line-height: 1;
  }

  .idb-import-badge.is-imported {
    color: var(--idb-success);
  }

  .idb-import-badge.is-candidate {
    color: var(--idb-warning);
  }

  .idb-preview-scroll {
    padding: 16px;
    color: var(--idb-text);
    font-size: var(--b2s-fs-sm);
  }

  .idb-preview-empty {
    min-height: 180px;
    padding: 10px;
    border: 1px dashed var(--idb-border-strong);
    border-radius: var(--b2s-radius-md);
    background: var(--idb-panel-bg);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
  }

  .idb-preview-empty span {
    color: var(--idb-text-muted);
    font-size: var(--b2s-fs-sm);
    line-height: 1.35;
  }

  .idb-preview-fields {
    display: grid;
    gap: 8px;
    margin: 0;
  }

  .idb-preview-fields dt {
    font-size: var(--b2s-fs-xs);
    font-weight: 400;
    color: var(--idb-text-muted);
  }

  .idb-preview-fields dd {
    margin: 0;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
    line-height: 1.15;
    color: var(--idb-heading);
    overflow-wrap: anywhere;
  }

  .idb-snapshot-delta {
    margin-top: 16px;
  }

  .idb-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
  }

  .idb-selected-panel,
  .idb-role-panel {
    padding: 16px;
    border-top: 1px solid var(--idb-border);
    background: var(--idb-panel-head-bg);
  }

  .idb-selected-panel {
    max-height: 220px;
    overflow: auto;
  }

  .idb-selected-list {
    display: flex;
    flex-direction: column;
    gap: 7px;
    margin-top: 8px;
  }

  .idb-role-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
    font-size: var(--b2s-fs-sm);
  }

  .idb-role-key {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .idb-role-row input {
    accent-color: var(--idb-accent);
  }

  .idb-error {
    margin-top: 16px;
    padding: 8px 12px;
    border: 1px solid #ffe69c;
    border-radius: var(--b2s-radius-sm);
    background: #fff3cd;
    color: #664d03;
    font-size: var(--b2s-fs-sm);
  }

  .idb-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 7px;
    padding: 10px 14px;
    border-top: 1px solid var(--idb-border);
    background: var(--idb-panel-head-bg);
  }

  .idb-footer-count {
    margin-right: auto;
  }

  @media (max-width: 1180px) {
    .idb-layout {
      grid-template-columns: 28% 44% 28%;
      height: auto;
      min-height: 56vh;
    }
  }

  @media (max-width: 920px) {
    :global(.b2s-modal.idb-dialog) {
      width: 96vw;
    }

    .idb-toolbar-grid {
      grid-template-columns: 1fr;
    }

    .idb-toolbar-actions {
      justify-content: flex-start;
    }

    .idb-layout {
      grid-template-columns: 1fr;
      height: auto;
    }

    .idb-results-panel {
      border-inline: 0;
      border-block: 1px solid var(--idb-border);
    }
  }
</style>
