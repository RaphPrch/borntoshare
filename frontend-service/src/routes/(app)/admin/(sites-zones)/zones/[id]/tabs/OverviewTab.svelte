<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import { previewRootGroups } from '$lib/api/naming-policies';
  import type { ZoneSummary } from '$lib/components/zones/zone-summary';

  /**
   * Overview of a zone in cards: its servers (file servers and DFS namespaces), its folders to review,
   * its governance (OU, naming, gaps, guardians, directories) (its activity has its own tab).
   */
  export let zoneId: number | null = null;
  export let summary: ZoneSummary;
  export let namingTemplateLabel = '';
  export let provisioningOu = '';
  export let minGuardians = 2;
  export let directories: string[] = [];
  export let activity: any[] = [];
  export let onOpenEndpoint: ((endpointId: number) => void) | null = null;
  export let onOpenRoot: ((rootId: number) => void) | null = null;
  export let onOpenFolders: (() => void) | null = null;
  export let onOpenProvisioning: (() => void) | null = null;
  export let onAddServer: (() => void) | null = null;

  type Filter = 'all' | 'bad' | 'filer' | 'dfs';
  let query = '';
  let filter: Filter = 'all';

  const STATE: Record<string, { label: () => string; tone: string }> = {
    reachable: { label: () => t('Reachable'), tone: 'ok' },
    unreachable: { label: () => t('Unreachable'), tone: 'bad' },
    checking: { label: () => t('Checking…'), tone: 'n' },
    disabled: { label: () => t('Disabled'), tone: 'n' },
    unknown: { label: () => t('Not tested'), tone: 'n' }
  };

  $: servers = summary.servers;
  $: segments = [
    { key: 'all' as Filter, label: t('All'), count: servers.length },
    { key: 'bad' as Filter, label: t('Unreachable'), count: summary.unreachable.length },
    { key: 'filer' as Filter, label: t('Files'), count: summary.files.length },
    { key: 'dfs' as Filter, label: t('DFS'), count: summary.dfs.length }
  ].filter((segment) => segment.key === 'all' || segment.count > 0);
  $: visible = servers
    .filter((server) => filter === 'all' || (filter === 'bad' ? server.state === 'unreachable' : filter === 'dfs' ? server.dfs : !server.dfs))
    .filter((server) => `${server.name} ${server.host}`.toLowerCase().includes(query.trim().toLowerCase()));

  // An example of group name and the gaps to the saved rule, read once per zone and rule
  let example = '';
  let gaps = 0;
  let exampleKey = '';
  $: if (zoneId && `${zoneId}|${namingTemplateLabel}` !== exampleKey) void loadExample(`${zoneId}|${namingTemplateLabel}`);
  async function loadExample(key: string) {
    exampleKey = key;
    try {
      const result = await previewRootGroups(fetch, { zone_id: zoneId, limit: 1 });
      if (key !== exampleKey) return;
      example = result?.items?.[0]?.read_group ?? '';
      gaps = Number(result?.drift_total ?? 0);
    } catch {
      example = '';
      gaps = 0;
    }
  }

  $: lastChange = activity[0] ?? null;
</script>

<div class="zo">
  <div class="zo__col">
    <section class="zo__card" aria-label={t('Servers of the zone')}>
      <header><h2>{t('Servers of the zone')}</h2>{#if onAddServer}<button type="button" class="b2s-link-btn" on:click={onAddServer}>+ {t('Add')}</button>{/if}</header>
      {#if servers.length}
        <div class="zo__tools">
          <input class="b2s-input" type="search" aria-label={t('Filter the servers')} placeholder={t('Filter the servers…')} bind:value={query} />
          <div class="zo__seg" role="group" aria-label={t('Filter by state')}>
            {#each segments as segment (segment.key)}
              <button type="button" class:on={filter === segment.key} aria-pressed={filter === segment.key} on:click={() => (filter = segment.key)}>{segment.label}<span>{segment.count}</span></button>
            {/each}
          </div>
        </div>
        {#each visible as server (server.id)}
          {@const state = server.dfs ? { label: () => t('Namespace'), tone: 'r' } : STATE[server.state]}
          <button type="button" class="zo__srv" on:click={() => onOpenEndpoint?.(server.id)}>
            <i class={`bi ${server.dfs ? 'bi-diagram-3' : 'bi-hdd-network'}`} aria-hidden="true"></i>
            <span class="zo__name"><strong>{server.name}</strong><small class="mono">{server.host}</small></span>
            <span class="zo__health">
              <small>
                {#if server.dfs}{t('DFS folders on its target servers')}
                {:else if server.roots}{server.review ? t('{count} folders · {review} to review', { count: server.roots, review: server.review }) : t('{count} folders', { count: server.roots })}
                {:else}{t('No managed folder')}{/if}
              </small>
              {#if !server.dfs && server.roots}
                <span class="zo__bar" aria-hidden="true"><i style={`flex:${server.roots - server.review}`}></i><i class:bad={server.state === 'unreachable'} class="warn" style={`flex:${server.review}`}></i></span>
              {/if}
            </span>
            <span class="zo__state">
              <span class={`zo__pill is-${state.tone}`}>{state.label()}</span>
              <small>{server.lastProbeAt ? timeAgo(server.lastProbeAt) : server.dfs ? '' : t('never')}</small>
            </span>
          </button>
        {:else}
          <p class="zo__muted">{t('No server matches this search.')}</p>
        {/each}
      {:else}
        <p class="zo__muted">{t('No server in this zone yet: add a file server or a DFS namespace.')}</p>
      {/if}
    </section>

    {#if summary.review.length}
      <section class="zo__card" aria-label={t('Folders to review')}>
        <header>
          <h2>{t('Folders to review')}</h2>
          {#if onOpenFolders}<button type="button" class="b2s-link-btn" on:click={onOpenFolders}>{t('The {count} in the table', { count: summary.review.length })} ›</button>{/if}
        </header>
        {#each summary.review.slice(0, 5) as root (root.id)}
          <div class="zo__root">
            <span class="zo__name"><strong>{root.name}</strong><small class="mono" title={root.path}>{root.path}</small></span>
            <span class={`zo__pill is-${root.blocking ? 'bad' : 'warn'}`}>{root.label}</span>
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={() => onOpenRoot?.(root.id)}>{t('Open')}</button>
          </div>
        {/each}
      </section>
    {/if}
  </div>

  <div class="zo__col">
    <section class="zo__card" aria-label={t('Governance')}>
      <header><h2>{t('Governance')}</h2>{#if onOpenProvisioning}<button type="button" class="b2s-link-btn" on:click={onOpenProvisioning}>{t('Provisioning')} ›</button>{/if}</header>
      <dl>
        <div><dt>{t('OU of the groups')}</dt><dd class="mono">{provisioningOu || t('Default OU of the directory')}</dd></div>
        <div><dt>{t('Naming')}</dt><dd><span class="mono">{namingTemplateLabel || t('Not set')}</span>{#if example}<small>{t('Example: {name}', { name: example })}</small>{/if}</dd></div>
        <div><dt>{t('Gaps')}</dt><dd class:warn={gaps > 0}>{gaps ? t('{count} folder(s) with groups off the rule', { count: gaps }) : t('none')}</dd></div>
        <div><dt>{t('Guardians')}</dt><dd>{t('{count} minimum per folder', { count: minGuardians })}</dd></div>
        {#if directories.length}<div><dt>{t('Directory')}</dt><dd>{directories.join(', ')}</dd></div>{/if}
        {#if lastChange?.created_at}
          <div><dt>{t('Last change')}</dt><dd>{lastChange.actor_display_name ?? lastChange.actor_display ?? lastChange.actor_username ?? '—'}<small>{timeAgo(lastChange.created_at)}</small></dd></div>
        {/if}
      </dl>
    </section>

  </div>
</div>

<style>
  .zo { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 14px; align-items: start; }
  .zo__col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .zo__card { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .zo__card header { display: flex; align-items: center; gap: 12px; }
  .zo__card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .zo__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .zo__tools { display: flex; gap: 8px; align-items: center; }
  .zo__tools .b2s-input { flex: 1; max-width: 260px; }
  .zo__seg { display: flex; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .zo__seg button { padding: 4px 10px; border: 0; border-radius: var(--b2s-radius-sm); background: none; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); white-space: nowrap; cursor: pointer; }
  .zo__seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; }
  .zo__seg span { margin-left: 5px; opacity: 0.7; }
  .zo__srv { display: grid; grid-template-columns: 22px minmax(0, 1.1fr) minmax(0, 1fr) auto; gap: 12px; align-items: center; width: 100%; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .zo__srv:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .zo__srv > i { color: var(--b2s-color-text-muted); }
  .zo__name { display: flex; flex-direction: column; min-width: 0; }
  .zo__name strong { font-weight: 500; font-size: var(--b2s-fs-sm); }
  .zo__name small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .zo__health { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .zo__health small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .zo__bar { display: flex; gap: 2px; height: 4px; overflow: hidden; border-radius: 99px; }
  .zo__bar i { display: block; min-width: 0; border-radius: 99px; background: var(--b2s-color-success); }
  .zo__bar i.warn { background: var(--b2s-color-warning); }
  .zo__bar i.bad { background: var(--b2s-color-danger); }
  .zo__state { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
  .zo__state small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .zo__pill { display: inline-flex; padding: 2px 9px; border-radius: 99px; font-size: var(--b2s-fs-xs); font-weight: 500; white-space: nowrap; }
  .zo__pill.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .zo__pill.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .zo__pill.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .zo__pill.is-r { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .zo__pill.is-n { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .zo__root { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; align-items: center; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); }
  .zo__card header + .zo__root { border-top: 0; }
  dl { margin: 0; }
  dl div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  dl div:first-child { border-top: 0; }
  dt { color: var(--b2s-color-text-muted); }
  dd { display: flex; flex-direction: column; gap: 2px; margin: 0; min-width: 0; overflow-wrap: anywhere; }
  dd small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  dd.warn { color: var(--b2s-color-warning-strong); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
