  <script lang="ts">
  import { toast } from "$lib/utils/toast";
  import { runProbeWithPolling } from "$lib/probe/probe-runner";
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    parseStorageEndpointProbeRoots,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from "$lib/probe/storage-endpoint-probe";
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import StorageRootDrawerShell from '$lib/components/storage-roots/StorageRootDrawerShell.svelte';

  type StorageRootForm = {
    name: string;
    display_name?: string | null;
    storage_endpoint_id: number;
    root_path: string;
    discovery_roots?: string[];
    path?: string | null;
    status?: string | null;
  };

  export let open = false;
  export let mode: "create" | "edit" | "delete" = "create";
  export let root: any | null = null;

  // Select data
  export let endpoints: Array<{
    id?: number;
    storage_endpoint_id?: number;
    name?: string;
    storage_endpoint_name?: string;
    code?: string;
    host?: string;
    port?: number;
    auth_user?: string;
    username?: string;
    bind_dn?: string;
    user?: string;
    auth_secret_ref?: string;
    bind_password_ref?: string;
    protocol?: string;
    type?: string;
  }> = [];
  export let endpointId: number | null = null;


  export let onClose: () => void;
  export let onSubmit: (payload: StorageRootForm) => void;
  export let onDelete: () => void;

  let form: StorageRootForm = {
    name: "",
    display_name: "",
    storage_endpoint_id: 0,
    root_path: "",
    discovery_roots: [],
    path: "",
    status: "active"
  };

  let discoveryRootsText = "";
  let probeBusy = false;
  let discoverBusy = false;
  let probeOk = false;
  let probeError: string | null = null;
  let detectedRoots: string[] = [];
  let deleteConfirmation = "";

  const DELETE_CONFIRM_TOKEN = "DELETE";
  const drawerTitle = () =>
    mode === 'edit'
      ? 'Edit storage root'
      : mode === 'delete'
        ? 'Delete storage root'
        : 'Create storage root';

  const drawerSubtitle = () =>
    mode === 'delete'
      ? 'This action is irreversible. Confirm the deletion of this storage root.'
      : mode === 'edit'
        ? 'Update identity and root path of the selected storage root.'
        : 'Register a new governed storage root.';

  $: entityName = root?.display_name ?? root?.storage_root_name ?? root?.name ?? null;
  $: entityPath = root?.root_path ?? root?.locator ?? root?.path ?? null;

  const endpointIdOf = (endpoint: any): number =>
    Number(endpoint?.storage_endpoint_id ?? endpoint?.id ?? 0);

  const endpointLabel = (endpoint: any): string => {
    const id = endpointIdOf(endpoint);
    const code = String(endpoint?.code ?? "").trim();
    const name = String(endpoint?.name ?? endpoint?.storage_endpoint_name ?? endpoint?.label ?? "").trim();
    const base = name || (id > 0 ? `Endpoint #${id}` : "Endpoint");
    return code ? `${code} — ${base}` : base;
  };

  const selectedEndpoint = () => {
    const id = Number(form.storage_endpoint_id ?? 0);
    if (!Number.isFinite(id) || id <= 0) return null;
    return endpoints.find((e) => endpointIdOf(e) === id) ?? null;
  };

  const rootLabelFromPath = (value: string) => {
    const normalized = String(value ?? "").trim().replace(/[\\/]+$/, '');
    const chunks = normalized.split(/[\\/]/).filter(Boolean);
    return chunks[chunks.length - 1] ?? normalized;
  };

  $: if (open && mode !== "delete") {
    const displayName = root?.display_name ?? root?.storage_root_name ?? root?.name ?? "";
    const rootPath = root?.root_path ?? root?.locator ?? root?.path ?? "";

    form = {
      name: displayName,
      display_name: displayName,
      storage_endpoint_id: root?.storage_endpoint_id ?? endpointId ?? 0,
      root_path: rootPath,
      discovery_roots: rootPath ? [rootPath] : [],
      path: rootPath,
      status: root?.status ?? "active"
    };

    discoveryRootsText = rootPath;
    probeOk = false;
    probeError = null;
    detectedRoots = [];
  }

  $: if (open && mode === "delete") {
    deleteConfirmation = "";
  }

  const parseDiscoveryRoots = (value: string): string[] => {
    const parts = value
      .split(/\r?\n|,|;/)
      .map((item) => item.trim())
      .filter(Boolean);
    return [...new Set(parts)];
  };

  async function probeConnection() {
    const endpoint: any = selectedEndpoint();
    if (!endpoint) {
      toast.warning("Select an endpoint first");
      return;
    }

    const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Storage endpoint' });
    if (!validation.ok) {
      toast.error(validation.message ?? 'Endpoint must have SMB/CIFS host, username and bind_password_ref to run probe');
      return;
    }

    probeBusy = true;
    probeOk = false;
    probeError = null;
    try {
      const request = buildStorageEndpointProbeRequestFromEndpoint(endpoint, {
        discover: false,
        timeoutSec: 30,
        uiOrigin: 'admin'
      });

      const final = await runProbeWithPolling({
        fetchFn: fetch,
        request,
        intervalMs: 1500,
        maxAttempts: 80
      });

      if (!final.ok) throw new Error(final.errorMessage || 'Probe failed');
      probeOk = true;
      toast.success('Connection probe successful');
    } catch (e) {
      probeError = e?.message ?? 'Probe failed';
      toast.error(probeError);
    } finally {
      probeBusy = false;
    }
  }

  async function discoverRoots() {
    const endpoint: any = selectedEndpoint();
    if (!endpoint) {
      toast.warning("Select an endpoint first");
      return;
    }

    const probeConfig = resolveStorageEndpointProbeConfig(endpoint);
    const validation = validateStorageEndpointProbeConfig(probeConfig, { label: 'Storage endpoint' });
    if (!validation.ok) {
      toast.error(validation.message ?? 'Endpoint must have SMB/CIFS host, username and bind_password_ref to discover roots');
      return;
    }

    discoverBusy = true;
    probeError = null;
    try {
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

      if (!final.ok) throw new Error(final.errorMessage || 'Discovery failed');
      detectedRoots = parseStorageEndpointProbeRoots(final.result);
      if (detectedRoots.length === 0) {
        toast.warning('No roots discovered');
      } else {
        discoveryRootsText = detectedRoots.join('\n');
        if (!form.root_path) form.root_path = detectedRoots[0];
        toast.success(`${detectedRoots.length} roots discovered`);
      }
    } catch (e) {
      probeError = e?.message ?? 'Discovery failed';
      toast.error(probeError);
    } finally {
      discoverBusy = false;
    }
  }

  function useDiscoveredRoot(path: string) {
    const value = String(path ?? '').trim();
    if (!value) return;
    form.root_path = value;
    discoveryRootsText = value;
    const currentName = String(form.display_name ?? '').trim();
    if (!currentName) {
      form.display_name = rootLabelFromPath(value);
      form.name = form.display_name;
    }
  }

  function submit() {
    const displayName = (form.display_name ?? form.name ?? "").trim();
    const rootPath = (form.root_path ?? "").trim();
    const discoveryRoots = parseDiscoveryRoots(discoveryRootsText);

    if (mode === "edit") {
      if (!displayName || !rootPath) {
        toast.warning("Please fill required fields");
        return;
      }
    } else if (!form.storage_endpoint_id || discoveryRoots.length === 0) {
      toast.warning("Please fill required fields");
      return;
    }

    const resolvedFirstRoot = rootPath || discoveryRoots[0] || "";
    const resolvedName = displayName || rootLabelFromPath(resolvedFirstRoot);

    onSubmit({
      name: resolvedName,
      display_name: resolvedName,
      storage_endpoint_id: Number(form.storage_endpoint_id),
      root_path: resolvedFirstRoot,
      discovery_roots: discoveryRoots,
      path: resolvedFirstRoot,
      status: (form.status ?? "").trim() || null
    });
  }

  function confirmDelete() {
    if (deleteConfirmation.trim() !== DELETE_CONFIRM_TOKEN) {
      toast.warning('Type DELETE to confirm removal');
      return;
    }
    onDelete();
  }
</script>

{#if open}
  <StorageRootDrawerShell
    open={open}
    onClose={onClose}
    title={drawerTitle()}
    subtitle={drawerSubtitle()}
    ariaLabelledby="sr-edit-root-drawer-title"
    width="560px"
    topOffset="70px"
    showFooter={true}
  >
    <div class="sr-modal-content" style="padding: 0;">
      {#if mode === "delete"}
        <div class="sr-modal-info">
          <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
          <div>
            <strong>This deletion is irreversible.</strong>
            <div>The selected storage root will be permanently deleted.</div>
          </div>
        </div>

        <div class="sr-modal-field">
          <label>Storage Root</label>
          <div class="sr-input-icon">
            <i class="bi bi-folder2-open" aria-hidden="true"></i>
            <input value={entityName ?? "Storage Root"} readonly />
          </div>
        </div>

        <div class="sr-modal-field">
          <label>Root Path</label>
          <div class="sr-input-icon">
            <i class="bi bi-diagram-3" aria-hidden="true"></i>
            <input value={entityPath ?? "—"} readonly />
          </div>
        </div>

        <div class="sr-modal-field">
          <label for="sr-delete-confirm">Type DELETE to confirm</label>
          <input
            id="sr-delete-confirm"
            bind:value={deleteConfirmation}
            placeholder="DELETE"
            autocomplete="off"
            spellcheck="false"
          />
          <small class="sr-muted">Deletion is enabled only when the exact keyword is entered.</small>
        </div>
      {:else}
        <div class="sr-modal-info">
          <i class="bi bi-info-circle" aria-hidden="true"></i>
          <div>
            <strong>Register a new governed storage root.</strong>
            <div>
              {mode === "edit"
                ? "Only display name and path can be edited here."
                : "No access will be modified at this stage. Fill endpoint name and discovery roots."}
            </div>
          </div>
        </div>

        <div class="sr-modal-field">
          <label for="sr-endpoint">Endpoint Name</label>
          <div class="sr-input-icon">
            <i class="bi bi-hdd" aria-hidden="true"></i>
            <select id="sr-endpoint" bind:value={form.storage_endpoint_id} disabled={mode === "edit"}>
              <option value={0}>Select…</option>
              {#each endpoints as e (endpointIdOf(e))}
                {@const id = endpointIdOf(e)}
                <option value={id}>{endpointLabel(e)}</option>
              {/each}
            </select>
          </div>
          {#if mode === "edit"}
            <small class="sr-muted">Endpoint is read-only in edit mode.</small>
          {/if}
        </div>

        {#if mode === "edit"}
          <div class="sr-modal-field">
            <label for="sr-locator">Root Path</label>
            <input id="sr-locator" bind:value={form.root_path} placeholder="/mnt/finance" />
          </div>
        {:else}
          <div class="sr-modal-field">
            <label>Connection checks</label>
            <div class="sr-modal-inline-actions">
              <EntityActionButton compact={true} variant="secondary" icon="bi-activity" label={probeBusy ? 'Running probe…' : 'Probe connection'} busy={probeBusy} disabled={probeBusy || discoverBusy || !form.storage_endpoint_id} onClick={probeConnection} />
              <EntityActionButton compact={true} variant="secondary" icon="bi-search" label={discoverBusy ? 'Discovering…' : 'Discover roots'} busy={discoverBusy} disabled={discoverBusy || probeBusy || !form.storage_endpoint_id} onClick={discoverRoots} />
            </div>
            {#if probeOk}
              <small class="sr-muted" style="color: #15803d;">Connection successful.</small>
            {/if}
            {#if probeError}
              <small class="sr-muted" style="color: #b91c1c;">{probeError}</small>
            {/if}
          </div>

          <div class="sr-modal-field">
            <label for="sr-discovery-roots">Discovery Roots</label>
            <textarea
              id="sr-discovery-roots"
              bind:value={discoveryRootsText}
              placeholder="\\\\server\\finance&#10;\\\\server\\hr"
              rows="4"
            ></textarea>
            <small class="sr-muted">One root path per line (or separated by comma/semicolon).</small>

            {#if detectedRoots.length > 0}
              <div class="sr-discovered-roots">
                <div class="sr-discovered-title">Roots available on selected endpoint</div>
                <div class="sr-discovered-list">
                  {#each detectedRoots as rootPath}
                    <button class="sr-discovered-item" type="button" on:click={() => useDiscoveredRoot(rootPath)} title={rootPath}>
                      <i class="bi bi-folder2-open" aria-hidden="true"></i>
                      <span>{rootPath}</span>
                    </button>
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        {/if}

        <div class="sr-modal-field">
          <label for="sr-name">{mode === "edit" ? "Display Name" : "Name"}</label>
          <input id="sr-name" bind:value={form.display_name} placeholder="Enter name" />
        </div>

        <div class="sr-modal-field">
          <label for="sr-status">Status</label>
          <select id="sr-status" bind:value={form.status} disabled={mode === "edit"}>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </select>
          {#if mode === "edit"}
            <small class="sr-muted">Status is managed from the action buttons.</small>
          {/if}
        </div>
      {/if}
    </div>

    <svelte:fragment slot="footer">
      <div class="sr-modal-actions">
        <EntityActionButton compact={true} variant="secondary" label="Cancel" onClick={onClose} />
        {#if mode === "delete"}
          <EntityActionButton
            compact={true}
            variant="danger"
            icon="bi-trash"
            label="Delete storage root"
            disabled={deleteConfirmation.trim() !== DELETE_CONFIRM_TOKEN}
            onClick={confirmDelete}
          />
        {:else if mode === "edit"}
          <EntityActionButton compact={true} variant="primary" icon="bi-check2" label="Save changes" onClick={submit} />
        {:else}
          <EntityActionButton compact={true} variant="primary" icon="bi-plus-lg" label="Create storage root" onClick={submit} />
        {/if}
      </div>
    </svelte:fragment>
  </StorageRootDrawerShell>
{/if}

<style>
  .sr-modal-inline-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .sr-discovered-roots {
    margin-top: 10px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 10px;
    padding: 10px;
    background: rgba(248, 250, 252, 0.55);
  }

  .sr-discovered-title {
    font-size: 12px;
    color: #334155;
    margin-bottom: 8px;
    font-weight: 600;
  }

  .sr-discovered-list {
    display: grid;
    gap: 6px;
    max-height: 180px;
    overflow: auto;
  }

  .sr-discovered-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 8px;
    background: #fff;
    color: #0f172a;
    padding: 7px 9px;
    text-align: left;
  }

  .sr-discovered-item:hover {
    border-color: rgba(59, 130, 246, 0.6);
    background: rgba(239, 246, 255, 0.8);
  }

  .sr-discovered-item span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
