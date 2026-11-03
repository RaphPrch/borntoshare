<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { humanizeFileServerMessage } from '$lib/errors/file-server';
  import { buildStorageEndpointProbeRequestFromEndpoint, parseStorageEndpointProbeRoots } from '$lib/jobs/storage-endpoint-probe';
  import { runProbeWithPolling, syncStorageRootDiscoveryForEndpoint } from '$lib/jobs/probe-runner';
  import { formatDateTime } from '$lib/utils/format';
  import { toast } from '$lib/stores/toast';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { deleteStorageEndpointShare } from '$lib/api/storage-endpoints';
  import { reportUiError } from '$lib/errors/report';

  /** Shares found on the server by its last search: the managed ones, and those to add (one by one, or several at once). */
  export let endpoint: Record<string, any>;
  export let discoveredAt: string | null = null;
  export let onChanged: () => void = () => {};

  type Share = { name: string; root_path: string; managed: boolean; managed_below?: number };
  let shares: Share[] = [];
  let loading = true;
  let searching = false;
  let error = '';
  let query = '';
  let filter: 'new' | 'managed' | 'all' = 'new';
  let adding: Record<string, boolean> = {};

  $: id = Number(endpoint?.id ?? endpoint?.storage_endpoint_id ?? 0);
  $: counts = { new: shares.filter((s) => !s.managed).length, managed: shares.filter((s) => s.managed).length, all: shares.length };
  $: visible = shares
    .filter((s) => filter === 'all' || (filter === 'new' ? !s.managed : s.managed))
    .filter((s) => `${s.name} ${s.root_path}`.toLowerCase().includes(query.trim().toLowerCase()));

  async function load() {
    loading = true;
    try {
      const answer = await apiGetData<{ items: Share[] }>(fetch, '/storage-roots/discovered', { storage_endpoint_id: id });
      shares = answer.items;
    } catch (e) {
      error = e instanceof Error ? e.message : t('Unable to read the folders of this server.');
    } finally {
      loading = false;
    }
  }

  async function searchAgain() {
    searching = true;
    error = '';
    try {
      const final: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: buildStorageEndpointProbeRequestFromEndpoint(endpoint as any, { discover: true, timeoutSec: 30, uiOrigin: 'admin' }),
        intervalMs: 1500,
        maxAttempts: 80
      });
      if (!final.ok) throw new Error(humanizeFileServerMessage(t(String(final.errorMessage ?? 'Unable to read the folders of this server.'))));
      await syncStorageRootDiscoveryForEndpoint(fetch, id, final.result);
      if (!parseStorageEndpointProbeRoots(final.result).length && final.result?.details?.discovery_complete === false) {
        throw new Error(humanizeFileServerMessage(t(String(final.result?.message ?? 'Unable to read the folders of this server.'))));
      }
      await load();
      onChanged();
    } catch (e) {
      error = e instanceof Error ? e.message : t('Unable to read the folders of this server.');
    } finally {
      searching = false;
    }
  }

  async function add(share: Share) {
    adding = { ...adding, [share.root_path]: true };
    try {
      const answer = await apiPostData<{ created: unknown[]; failed: { message: string }[] }>(fetch, '/storage-roots/bulk', {
        items: [{ storage_endpoint_id: id, name: share.name, root_path: share.root_path }]
      });
      if (answer.failed.length) throw new Error(t(answer.failed[0].message));
      shares = shares.map((row) => (row.root_path === share.root_path ? { ...row, managed: true } : row));
      toast.success(t('{name} is now managed.', { name: share.name }));
      onChanged();
    } catch (e) {
      reportUiError(e, t('Creation failed'), 'storage-endpoint.share-manage');
    } finally {
      adding = { ...adding, [share.root_path]: false };
    }
  }

  // A share that BornToShare does not manage can be removed from the server; its files stay there
  let toDelete: Share | null = null;
  let deleting = false;
  // Its folder too, when empty (rmdir on the server refuses a folder that still holds files)
  let removeEmptyFolder = true;

  async function confirmDelete() {
    const share = toDelete;
    if (!share) return;
    deleting = true;
    try {
      const done = await deleteStorageEndpointShare(fetch, id, share.name, removeEmptyFolder);
      shares = shares.filter((row) => row.root_path !== share.root_path);
      toast.success(
        removeEmptyFolder && !done.folder_removed
          ? t('Share {name} deleted; its folder is kept because it is not empty.', { name: share.name })
          : t('Share {name} deleted from the file server.', { name: share.name })
      );
      toDelete = null;
      onChanged();
    } catch (e) {
      reportUiError(e, t('The share was not deleted.'), 'storage-endpoint.share-delete');
    } finally {
      deleting = false;
    }
  }

  onMount(load);
</script>

<div class="head">
  <small class="muted">{discoveredAt ? t('Last search on {date}', { date: formatDateTime(discoveredAt) }) : t('This server has never been searched.')}</small>
  <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={searching} on:click={searchAgain}>{searching ? t('Searching…') : t('Search the server again')}</button>
  {#if counts.new > 1}<a class="b2s-btn b2s-btn-primary b2s-btn-sm" href={`/storage-roots/add?endpoint=${id}`}>{t('Add several')}</a>{/if}
</div>
{#if error}<InlineAlert tone="error">{error}</InlineAlert>{/if}
<div class="tools">
  <input class="b2s-input" aria-label={t('Filter the shares')} placeholder={t('Filter the shares…')} bind:value={query} />
  <div class="seg">
    {#each [['new', t('Not managed')], ['managed', t('Managed')], ['all', t('All')]] as [key, label]}
      <button type="button" class:on={filter === key} on:click={() => (filter = key as typeof filter)}>{label} <span>{counts[key]}</span></button>
    {/each}
  </div>
</div>
{#if loading}
  <p class="empty">{t('Loading…')}</p>
{:else if visible.length}
  <ul class="list">
    {#each visible as share (share.root_path)}
      <li>
        <span class="name"><strong>{share.name}</strong></span>
        {#if share.managed}
          <span class="pill">{t('Managed')}</span>
        {:else}
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={adding[share.root_path]} on:click={() => add(share)}>{adding[share.root_path] ? t('Adding…') : t('Manage')}</button>
          {#if share.managed_below}
            <span class="muted" title={t('BornToShare manages folders in this share: remove them from BornToShare first.')}>{t('{count} managed folder(s)', { count: share.managed_below })}</span>
          {:else}
            <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" aria-label={t('Delete the share {name}', { name: share.name })} title={t('Delete the share')} on:click={() => (toDelete = share)}><i class="bi bi-trash" aria-hidden="true"></i></button>
          {/if}
        {/if}
      </li>
    {/each}
  </ul>
{:else}
  <p class="empty">{shares.length ? t('No share matches this search.') : t('No share found: search the server, or create a share.')}</p>
{/if}

<ConfirmActionModal
  open={Boolean(toDelete)}
  onClose={() => (toDelete = null)}
  onConfirm={confirmDelete}
  severity="danger"
  confirmVariant="danger"
  title={t('Delete the share {name}?', { name: toDelete?.name ?? '' })}
  subtitle={toDelete?.root_path ?? null}
  impactTitle={t('Impact')}
  impactItems={[
    t('The share is removed from the file server: its users lose the path.'),
    t('Files are never deleted: a folder that is not empty stays on the server.'),
    t('Refused while BornToShare manages a folder in it.')
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Delete the share')}
  confirmBusyLabel={t('Deleting…')}
  busy={deleting}
  requireTextConfirm={true}
  requiredText={toDelete?.name ?? ''}
  textConfirmLabel={t('Type the name of the share to confirm')}
  textConfirmPlaceholder={toDelete?.name ?? ''}
>
  <label class="also">
    <input type="checkbox" bind:checked={removeEmptyFolder} />
    <span>{t('Also delete its folder if it is empty')}</span>
  </label>
</ConfirmActionModal>

<style>
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .head small { margin-right: auto; }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .tools { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .seg { display: flex; flex: none; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .seg button { padding: 4px 9px; border: 0; border-radius: var(--b2s-radius-sm); background: transparent; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); cursor: pointer; }
  .seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .seg span { opacity: 0.7; }
  .list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .list li { display: flex; align-items: center; gap: 12px; padding: 7px 12px; }
  .list li + li { border-top: 1px solid var(--b2s-color-border); }
  .name { flex: 1; min-width: 0; }
  .name strong { font-weight: 500; }
  .pill { padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); font-size: var(--b2s-font-micro); font-weight: 500; }
  .empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
  .also { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
</style>
