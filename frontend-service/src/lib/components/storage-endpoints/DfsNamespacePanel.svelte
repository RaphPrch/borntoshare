<script lang="ts">
  import { t } from '$lib/i18n';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import type { DfsInfo, DfsLink } from './dfs-namespace';

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
  .act { text-align: right; }
  .link { font-size: var(--b2s-text-sm); }
  .more { width: 100%; margin-top: 8px; padding: 8px; border: 1px dashed var(--b2s-color-border-mid); border-radius: var(--b2s-radius-md); background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .empty { padding: 20px; text-align: center; color: var(--b2s-color-text-muted); }
</style>
