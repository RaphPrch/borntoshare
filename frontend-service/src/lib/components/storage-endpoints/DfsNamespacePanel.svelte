<script lang="ts">
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { humanizeFileServerMessage } from '$lib/errors/file-server';
  import { runProbeWithPolling } from '$lib/jobs/probe-runner';
  import { formatDateTime } from '$lib/utils/format';
  import { toast } from '$lib/stores/toast';

  /** A DFS namespace: its folders, the file server folders they lead to, and what is managed. Hundreds stay readable. */
  export let endpoint: Record<string, any>;
  export let onChanged: () => void = () => {};
  /** The namespace path, once read, for the page header. */
  export let namespacePath = '';

  type Target = { unc: string; server: string; storage_endpoint_id: number | null; storage_endpoint_name: string | null; storage_root_id: number | null };
  type Link = { path: string; dfs_path: string; targets: Target[]; state: 'managed' | 'partial' | 'to_manage' | 'unknown_server' | 'no_target' };
  type Info = { path: string | null; type: string | null; root_targets: string[]; read_at: string | null; error: string | null; links: Link[] };

  const PAGE = 50;
  let info: Info | null = null;
  let loading = true;
  let error = '';
  let reading = false;
  let busy: Record<string, boolean> = {};
  let query = '';
  let filter: 'all' | 'todo' | 'managed' | 'unknown' = 'all';
  let shown = PAGE;

  $: id = Number(endpoint?.id ?? endpoint?.storage_endpoint_id ?? 0);
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
  $: servers = new Set(links.flatMap((link) => link.targets.map((target) => target.server.toLowerCase()))).size;

  const STATE: Record<Link['state'], { label: () => string; tone: string }> = {
    managed: { label: () => t('Managed'), tone: 'ok' },
    partial: { label: () => t('Partly managed'), tone: 'warn' },
    to_manage: { label: () => t('To manage'), tone: 'n' },
    unknown_server: { label: () => t('Server not declared'), tone: 'bad' },
    no_target: { label: () => t('No target'), tone: 'n' }
  };

  async function load() {
    loading = true;
    error = '';
    try {
      info = await apiGetData<Info>(fetch, `/storage-endpoints/${id}/dfs-links`);
      namespacePath = info?.path ?? '';
    } catch (e) {
      error = e instanceof Error ? e.message : t('Unable to read this namespace.');
    } finally {
      loading = false;
    }
  }

  async function readAgain() {
    if (!info?.path) return;
    reading = true;
    error = '';
    try {
      const final: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: {
          kind: 'storage-endpoint',
          protocol: 'dfs',
          scope: 'read',
          target: { host: String(endpoint.host ?? ''), port: Number(endpoint.port ?? 445), path: info.path },
          auth: { mode: 'ntlm', username: String(endpoint.bind_dn ?? endpoint.auth_username ?? ''), secret_ref: String(endpoint.bind_password_ref ?? endpoint.auth_secret_ref ?? '') },
          options: { timeout_sec: 120 },
          context: { ui_origin: 'admin', storage_endpoint_id: id }
        } as any,
        intervalMs: 1500,
        maxAttempts: 100
      });
      if (!final.ok) throw new Error(humanizeFileServerMessage(t(String(final.errorMessage ?? final.result?.message ?? 'The DFS server could not be read'))));
      const namespace = (final.result?.details?.namespaces ?? [])[0];
      if (!namespace) throw new Error(t('This namespace was not found on its server.'));
      await apiPostData(fetch, `/storage-endpoints/${id}/dfs-snapshot`, { namespace });
      await load();
      onChanged();
      toast.success(t('Namespace read again.'));
    } catch (e) {
      error = e instanceof Error ? e.message : t('Unable to read this namespace.');
    } finally {
      reading = false;
    }
  }

  async function manage(paths: string[]) {
    const key = paths.length === 1 ? paths[0] : '*';
    busy = { ...busy, [key]: true };
    try {
      const answer = await apiPostData<{ managed: { path: string; created: number[] }[]; failed: { path: string; message: string }[] }>(
        fetch, `/storage-endpoints/${id}/dfs-links/manage`, { paths }
      );
      const created = answer.managed.reduce((sum, row) => sum + row.created.length, 0);
      if (answer.failed.length) toast.warning(t('{count} DFS folder(s) refused: {message}', { count: answer.failed.length, message: t(answer.failed[0].message) }));
      if (created) toast.success(t('{count} folder(s) now managed.', { count: created }));
      await load();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('Creation failed'));
    } finally {
      busy = { ...busy, [key]: false };
    }
  }

  // reload when another namespace is opened from the sidebar
  $: if (id) void load();
</script>

{#if loading}
  <p class="empty">{t('Loading…')}</p>
{:else if info}
  <div class="head">
    <div>
      <small class="muted">
        {info.type === 'domain' ? t('Domain namespace') : t('Standalone namespace')}
        · {t('root on {servers}', { servers: info.root_targets.map((target) => target.split('\\').filter(Boolean)[0]).join(', ') || '—' })}
        · {info.read_at ? t('read on {date}', { date: formatDateTime(info.read_at) }) : t('never read')}
      </small>
    </div>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={reading} on:click={readAgain}>{reading ? t('Reading…') : t('Read the namespace again')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={!manageable.length || busy['*']} on:click={() => manage(manageable.map((link) => link.path))}>
      {t('Manage the {count} to manage', { count: manageable.length })}
    </button>
  </div>
  {#if error || info.error}<InlineAlert tone="error">{error || info.error}</InlineAlert>{/if}

  <dl class="stats">
    <div><dt>{t('DFS folders')}</dt><dd>{links.length}</dd></div>
    <div><dt>{t('Managed')}</dt><dd>{counts.managed}</dd></div>
    <div><dt>{t('To manage')}</dt><dd class:warn={counts.todo > 0}>{counts.todo}</dd></div>
    <div><dt>{t('Target servers')}</dt><dd>{servers}{#if counts.unknown}<small class="bad">{t('{count} not declared', { count: counts.unknown })}</small>{/if}</dd></div>
  </dl>

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
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy[link.path]} on:click={() => manage([link.path])}>{t('Manage')}</button>
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

<style>
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .head > div { display: flex; flex-direction: column; margin-right: auto; min-width: 0; }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); margin: 0 0 14px; border-top: 1px solid var(--b2s-color-border); border-bottom: 1px solid var(--b2s-color-border); }
  .stats div { padding: 10px 14px; border-left: 1px solid var(--b2s-color-border); }
  .stats div:first-child { border-left: 0; padding-left: 0; }
  .stats dt { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .stats dd { margin: 0; font-size: 22px; font-weight: 600; }
  .stats dd.warn { color: var(--b2s-color-warning-strong); }
  .stats small { margin-left: 8px; font-size: var(--b2s-font-micro); font-weight: 500; }
  .bad { color: var(--b2s-color-danger-strong); }
  .tools { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .seg { display: flex; flex: none; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .seg button { padding: 4px 9px; border: 0; border-radius: var(--b2s-radius-sm); background: transparent; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); white-space: nowrap; cursor: pointer; }
  .seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .seg span { opacity: 0.7; }
  .list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .list li { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) 150px 150px; gap: 12px; align-items: center; padding: 8px 12px; }
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
