<script lang="ts">
  import { t } from '$lib/i18n';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { reportUiError } from '$lib/errors/report';
  import { toast } from '$lib/stores/toast';
  import { createDfsFolder, deleteDfsFolder, type DfsInfo, type DfsLink } from './dfs-namespace';

  /**
   * The DFS folders of a namespace and the file server folders they lead to, with what is managed.
   * Hundreds stay readable: filter, states, a page at a time. Read and managed by the page (dfs-namespace.ts).
   */
  export let endpoint: Record<string, any>;
  export let info: DfsInfo | null = null;
  export let loading = false;
  export let error = '';
  export let busy: Record<string, boolean> = {};
  export let onManage: (paths: string[]) => void = () => {};
  /** A DFS folder was created or removed: the page reads the namespace again. */
  export let onChanged: () => void = () => {};

  const PAGE = 50;
  let query = '';
  let filter: 'all' | 'todo' | 'managed' | 'unknown' = 'all';
  let shown = PAGE;

  $: links = info?.links ?? [];
  $: manageable = links.filter((link) => link.state === 'to_manage' || link.state === 'partial');
  $: counts = {
    all: links.length,
    todo: manageable.length,
    managed: links.filter((link) => link.state === 'managed').length,
    unknown: links.filter((link) => link.state === 'unknown_server').length
  };
  $: visible = links
    .filter((link) => filter === 'all' || (filter === 'todo' ? manageable.includes(link) : filter === 'managed' ? link.state === 'managed' : link.state === 'unknown_server'))
    .filter((link) => `${link.path} ${link.targets.map((target) => target.unc).join(' ')}`.toLowerCase().includes(query.trim().toLowerCase()));
  $: if (query || filter) shown = PAGE;

  $: endpointNumber = Number(endpoint?.id ?? endpoint?.storage_endpoint_id ?? 0);

  // A new DFS folder under the namespace, leading to a share
  let creating = false;
  let createOpen = false;
  let newFolder = '';
  let newTarget = '';
  let createError = '';
  $: canCreate = Boolean(newFolder.trim()) && /^\\\\[^\\]+\\[^\\]+/.test(newTarget.trim());

  function openCreate() {
    newFolder = '';
    newTarget = '';
    createError = '';
    createOpen = true;
  }

  async function submitCreate() {
    creating = true;
    createError = '';
    try {
      const done = await createDfsFolder(fetch, endpointNumber, newFolder.trim(), newTarget.trim());
      toast.success(t('DFS folder {path} created.', { path: done.path }));
      createOpen = false;
      onChanged();
    } catch (e) {
      createError = reportUiError(e, t('The DFS folder was not created.'), 'storage-endpoint.dfs-folder-create');
    } finally {
      creating = false;
    }
  }

  // A DFS folder that BornToShare does not manage can be removed; the shares behind it stay
  let toDelete: DfsLink | null = null;
  let deleting = false;

  async function confirmDelete() {
    const link = toDelete;
    if (!link) return;
    deleting = true;
    try {
      await deleteDfsFolder(fetch, endpointNumber, link.path);
      toast.success(t('DFS folder {path} deleted.', { path: link.dfs_path || link.path }));
      toDelete = null;
      onChanged();
    } catch (e) {
      reportUiError(e, t('The DFS folder was not deleted.'), 'storage-endpoint.dfs-folder-delete');
    } finally {
      deleting = false;
    }
  }

  const STATE: Record<DfsLink['state'], { label: () => string; tone: string }> = {
    managed: { label: () => t('Managed'), tone: 'ok' },
    partial: { label: () => t('Partly managed'), tone: 'warn' },
    to_manage: { label: () => t('To manage'), tone: 'n' },
    unknown_server: { label: () => t('Server not declared'), tone: 'bad' },
    no_target: { label: () => t('No target'), tone: 'n' }
  };
</script>

<section class="card" aria-label={t('DFS folders')}>
  <header>
    <h2>{t('DFS folders')}</h2>
    {#if info}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={openCreate}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('New DFS folder')}</button>
    {/if}
  </header>
{#if loading && !info}
  <p class="empty">{t('Loading…')}</p>
{:else if info}
  {#if error || info.error}<InlineAlert tone="error">{error || info.error}</InlineAlert>{/if}
  <div class="tools">
    <input class="b2s-input" aria-label={t('Filter the DFS folders')} placeholder={t('Filter the DFS folders…')} bind:value={query} />
    <div class="seg" role="group" aria-label={t('Filter by state')}>
      {#each [['all', t('All')], ['todo', t('To manage')], ['managed', t('Managed')], ['unknown', t('Server not declared')]] as [key, label]}
        <button type="button" class:on={filter === key} on:click={() => (filter = key as typeof filter)}>{label} <span>{counts[key]}</span></button>
      {/each}
    </div>
  </div>

  {#if visible.length}
    <ul class="list">
      {#each visible.slice(0, shown) as link (link.path)}
        {@const state = STATE[link.state]}
        <li>
          <span class="mono name" title={link.dfs_path}>{link.path}</span>
          <span class="targets">
            {#each link.targets as target}
              <small class="mono" class:unknown={!target.storage_endpoint_id} title={target.storage_endpoint_name ? t('On {name}', { name: target.storage_endpoint_name }) : t('Server not declared')}>{target.unc}</small>
            {:else}
              <small class="muted">—</small>
            {/each}
          </span>
          <span class={`pill pill--${state.tone}`}>{link.targets.length > 1 && link.state !== 'unknown_server' ? t('{label} · {count} targets', { label: state.label(), count: link.targets.length }) : state.label()}</span>
          <span class="act">
            {#if link.state === 'to_manage' || link.state === 'partial'}
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy[link.path]} on:click={() => onManage([link.path])}>{t('Manage')}</button>
            {:else if link.state === 'unknown_server'}
              <a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/admin/storage-endpoints/new${endpoint.zone_id ? `?zone=${endpoint.zone_id}` : ''}`}>{t('Declare the server')}</a>
            {:else if link.state === 'managed'}
              <a class="link" href={`/storage-roots?selected=${link.targets[0]?.storage_root_id}`}>{t('Open')}</a>
            {/if}
            {#if link.state !== 'managed' && link.state !== 'partial'}
              <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" aria-label={t('Delete the DFS folder {path}', { path: link.path })} title={t('Delete the DFS folder')} on:click={() => (toDelete = link)}><i class="bi bi-trash" aria-hidden="true"></i></button>
            {/if}
          </span>
        </li>
      {/each}
    </ul>
    {#if visible.length > shown}
      <button type="button" class="more" on:click={() => (shown += PAGE)}>{t('Show {count} more ({total} left)', { count: Math.min(PAGE, visible.length - shown), total: visible.length - shown })}</button>
    {/if}
  {:else}
    <p class="empty">{links.length ? t('No DFS folder matches this search.') : t('This namespace leads to no folder yet.')}</p>
  {/if}
{:else}
  <InlineAlert tone="error">{error}</InlineAlert>
{/if}
</section>

<AppModal open={createOpen} onClose={() => (createOpen = false)} title={t('New DFS folder')} subtitle={info?.path ?? null} iconClass="bi bi-diagram-3" closeOnBackdrop={false}>
  <div class="dfs-form">
    <label>
      {t('DFS folder')}
      <input class="b2s-input" bind:value={newFolder} maxlength="255" placeholder="Corporate\Finance" />
      <small>{t('Under {path}. Separate the levels with \\.', { path: info?.path ?? '' })}</small>
    </label>
    <label>
      {t('Target share')}
      <input class="b2s-input mono" bind:value={newTarget} maxlength="512" placeholder="\\FILER01\Finance" />
      <small>{t('The share the DFS folder leads to: create it first on its file server.')}</small>
    </label>
    {#if createError}<InlineAlert tone="error">{createError}</InlineAlert>{/if}
  </div>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-ghost" disabled={creating} on:click={() => (createOpen = false)}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" disabled={creating || !canCreate} on:click={submitCreate}>{creating ? t('Creating…') : t('Create the DFS folder')}</button>
  </svelte:fragment>
</AppModal>

<ConfirmActionModal
  open={Boolean(toDelete)}
  onClose={() => (toDelete = null)}
  onConfirm={confirmDelete}
  severity="danger"
  confirmVariant="danger"
  title={t('Delete the DFS folder {path}?', { path: toDelete?.path ?? '' })}
  subtitle={toDelete?.dfs_path ?? null}
  impactTitle={t('Impact')}
  impactItems={[
    t('Its users lose this DFS path.'),
    t('The shares it leads to and their files stay on their servers.'),
    t('Refused while BornToShare manages the folders behind it.')
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Delete the DFS folder')}
  confirmBusyLabel={t('Deleting…')}
  busy={deleting}
  requireTextConfirm={true}
  requiredText={toDelete?.path ?? ''}
  textConfirmLabel={t('Type the DFS folder to confirm')}
  textConfirmPlaceholder={toDelete?.path ?? ''}
/>

<style>
  .card { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .card header { display: flex; align-items: center; gap: 12px; }
  .card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .tools { display: flex; gap: 8px; align-items: center; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .seg { display: flex; flex: none; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .seg button { padding: 4px 9px; border: 0; border-radius: var(--b2s-radius-sm); background: transparent; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); white-space: nowrap; cursor: pointer; }
  .seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .seg span { opacity: 0.7; }
  .list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .list li { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) auto auto; gap: 12px; align-items: center; padding: 8px 12px; }
  .list li + li { border-top: 1px solid var(--b2s-color-border); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .name { font-size: var(--b2s-text-sm); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .targets { display: flex; flex-direction: column; min-width: 0; }
  .targets small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); }
  .targets .unknown { color: var(--b2s-color-danger-strong); }
  .pill { justify-self: start; padding: 1px 8px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-font-micro); font-weight: 500; white-space: nowrap; }
  .pill--ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .pill--warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .pill--bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .pill--n { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .act { display: flex; justify-content: flex-end; align-items: center; gap: 6px; }
  .dfs-form { display: grid; gap: 14px; }
  .dfs-form label { display: grid; gap: 6px; font-weight: 500; }
  .dfs-form small { color: var(--b2s-color-text-muted); font-weight: 400; }
  .link { font-size: var(--b2s-text-sm); }
  .more { width: 100%; margin-top: 8px; padding: 8px; border: 1px dashed var(--b2s-color-border-mid); border-radius: var(--b2s-radius-md); background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
</style>
