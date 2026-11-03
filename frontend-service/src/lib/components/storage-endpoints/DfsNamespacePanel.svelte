<script lang="ts">
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { t } from '$lib/i18n';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { reportUiError } from '$lib/errors/report';
  import { toast } from '$lib/stores/toast';
  import { apiGetData } from '$lib/api/client';
  import { listStorageEndpoints } from '$lib/api/storage-endpoints';
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
  export let onReadAgain: () => void = () => {};
  export let reading = false;

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

  let manageAfter = true;
  // The shares of the file servers of the zone, as DFS targets (\\\\FILER01\\Finance)
  let targetChoices: { value: string; label: string }[] = [];

  // A DFS target names its server as Windows knows it: the declared name when it is one, else its address
  const serverName = (ep: { name: string; host?: string | null }) =>
    /^[A-Za-z0-9-]{1,15}$/.test(ep.name) || /^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(ep.name) ? ep.name : String(ep.host ?? ep.name);

  async function loadTargets() {
    try {
      const servers = (await listStorageEndpoints(fetch)).filter(
        (ep) => String(ep.type).toLowerCase() !== 'dfs' && (!endpoint?.zone_id || Number(ep.zone_id) === Number(endpoint.zone_id))
      );
      const lists = await Promise.all(
        servers.map(async (ep) => {
          const answer = await apiGetData<{ items: { name: string }[] }>(fetch, '/storage-roots/discovered', { storage_endpoint_id: ep.id }).catch(() => ({ items: [] }));
          return answer.items.map((share) => ({ value: `\\\\${serverName(ep)}\\${share.name}`, label: `${ep.name} · ${share.name}` }));
        })
      );
      targetChoices = lists.flat();
    } catch {
      targetChoices = [];
    }
  }

  function openCreate() {
    newFolder = '';
    newTarget = '';
    createError = '';
    manageAfter = true;
    createOpen = true;
    void loadTargets();
  }

  async function submitCreate() {
    creating = true;
    createError = '';
    try {
      const done = await createDfsFolder(fetch, endpointNumber, newFolder.trim(), newTarget.trim());
      toast.success(t('DFS folder {path} created.', { path: done.path }));
      createOpen = false;
      // Managed at once: its target becomes a storage root (the page reads the namespace again)
      if (manageAfter) onManage([newFolder.trim().replace(/^\\+|\\+$/g, '')]);
      else onChanged();
    } catch (e) {
      createError = reportUiError(e, t('The DFS folder was not created.'), 'storage-endpoint.dfs-folder-create');
    } finally {
      creating = false;
    }
  }

  // Typed to confirm: the last level of the DFS folder (Finance for Corporate\\Finance)
  const lastLevel = (path: string | null | undefined) => String(path ?? '').split('\\').filter(Boolean).pop() ?? '';

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
      <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" disabled={reading} on:click={onReadAgain}><i class="bi bi-arrow-repeat" aria-hidden="true"></i>{reading ? t('Reading…') : t('Read again')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={openCreate}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('New DFS folder')}</button>
    {/if}
  </header>
{#if loading && !info}
  <p class="empty">{t('Loading…')}</p>
{:else if info}
  {#if error || info.error}<InlineAlert tone="error">{error || info.error}</InlineAlert>{/if}
  <div class="tools">
    <input class="b2s-input" aria-label={t('Filter the DFS folders')} placeholder={t('Filter the DFS folders…')} bind:value={query} />
    <SegmentedFilter ariaLabel={t('Filter by state')} bind:value={filter} options={[
      { key: 'all', label: t('All'), count: counts.all },
      { key: 'todo', label: t('To manage'), count: counts.todo },
      { key: 'managed', label: t('Managed'), count: counts.managed },
      { key: 'unknown', label: t('Server not declared'), count: counts.unknown }
    ]} />
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
      <input class="b2s-input mono" bind:value={newTarget} maxlength="512" placeholder="\\FILER01\Finance" list="dfs-target-choices" />
      <datalist id="dfs-target-choices">
        {#each targetChoices as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}
      </datalist>
      <small>{t('Choose a share of the zone, or type its path: create it first on its file server.')}</small>
    </label>
    <label class="check">
      <input type="checkbox" bind:checked={manageAfter} />
      <span>{t('Manage it in BornToShare right after')}</span>
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
  requiredText={lastLevel(toDelete?.path)}
  textConfirmLabel={t('Type the name to confirm')}
  textConfirmPlaceholder={lastLevel(toDelete?.path)}
/>

<style>
  .card { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .card header { display: flex; align-items: center; gap: 12px; }
  .card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .tools { display: flex; gap: 8px; align-items: center; }
  .tools .b2s-input { flex: 1; min-width: 0; }
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
  .dfs-form .check { display: flex; align-items: center; gap: 8px; font-weight: 400; }
  .link { font-size: var(--b2s-text-sm); }
  .more { width: 100%; margin-top: 8px; padding: 8px; border: 1px dashed var(--b2s-color-border-mid); border-radius: var(--b2s-radius-md); background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
</style>
