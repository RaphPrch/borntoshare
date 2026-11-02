<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
  import { normalizeProbeStatus } from '$lib/mappers/visual-state.mapper';

  /** Overview of a zone: its file servers and DFS namespaces in one list, its governance on the side. */
  export let endpoints: any[] = [];
  export let storageRoots: any[] = [];
  export let rootIdsWithAlerts: number[] = [];
  export let namingTemplateLabel = '';
  export let provisioningOu = '';
  export let probeResultsByEndpoint: Record<string, string> = {};
  export let lastChange: { actor?: string | null; at?: string | null } | null = null;
  export let onOpenEndpoint: ((endpointId: number) => void) | null = null;
  export let onOpenProvisioning: (() => void) | null = null;

  type Filter = 'all' | 'bad' | 'filer' | 'dfs';
  let query = '';
  let filter: Filter = 'all';

  const endpointId = (ep: any) => Number(ep?.id ?? ep?.storage_endpoint_id ?? 0);
  const isDfs = (ep: any) => String(ep?.endpoint_type ?? '').toLowerCase() === 'dfs';

  function stateOf(ep: any): { key: string; label: string; tone: string } {
    if (normalizeProbeStatus(probeResultsByEndpoint[String(endpointId(ep))] ?? '') === 'running') return { key: 'checking', label: t('Checking…'), tone: 'n' };
    const state = String(ep?.operational_state ?? '').toLowerCase();
    if (isDfs(ep)) return { key: 'dfs', label: t('Namespace'), tone: 'r' };
    if (state === 'reachable') return { key: 'ok', label: t('Reachable'), tone: 'ok' };
    if (state === 'unreachable') return { key: 'bad', label: t('Unreachable'), tone: 'bad' };
    if (state === 'disabled') return { key: 'off', label: t('Disabled'), tone: 'n' };
    return { key: 'unknown', label: t('Not tested'), tone: 'n' };
  }

  $: alertRoots = new Set(rootIdsWithAlerts);
  $: rows = endpoints.map((ep) => {
    const id = endpointId(ep);
    const roots = storageRoots.filter((root) => Number(root?.storage_endpoint_id ?? 0) === id);
    const toReview = roots.filter((root) => alertRoots.has(Number(root?.id ?? root?.storage_root_id ?? 0))).length;
    return { ep, id, dfs: isDfs(ep), roots: roots.length, toReview, state: stateOf(ep) };
  });
  $: counts = {
    all: rows.length,
    bad: rows.filter((row) => row.state.key === 'bad').length,
    filer: rows.filter((row) => !row.dfs).length,
    dfs: rows.filter((row) => row.dfs).length
  };
  $: visible = rows
    .filter((row) => filter === 'all' || (filter === 'bad' ? row.state.key === 'bad' : filter === 'dfs' ? row.dfs : !row.dfs))
    .filter((row) => `${row.ep?.name ?? ''} ${row.ep?.host ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()));
  $: segments = [
    { key: 'all' as Filter, label: t('All'), count: counts.all },
    { key: 'bad' as Filter, label: t('Unreachable'), count: counts.bad },
    { key: 'filer' as Filter, label: t('Files'), count: counts.filer },
    { key: 'dfs' as Filter, label: t('DFS'), count: counts.dfs }
  ].filter((segment) => segment.key === 'all' || segment.count > 0);

  function foldersLabel(row: { dfs: boolean; roots: number; toReview: number }) {
    if (row.dfs) return t('DFS folders on its target servers');
    if (!row.roots) return t('No managed folder');
    return row.toReview
      ? t('{count} folders · {review} to review', { count: row.roots, review: row.toReview })
      : t('{count} folders', { count: row.roots });
  }

  const lastTest = (ep: any) => (ep?.last_probe_at ? formatDateTime(ep.last_probe_at) : t('never'));
</script>

<div class="zo">
  <section class="zo__main" aria-label={t('Servers of the zone')}>
    {#if rows.length}
      <div class="zo__tools">
        <input class="b2s-input" type="search" aria-label={t('Filter the servers')} placeholder={t('Filter the servers…')} bind:value={query} />
        <div class="zo__seg" role="group" aria-label={t('Filter by state')}>
          {#each segments as segment (segment.key)}
            <button type="button" class:on={filter === segment.key} aria-pressed={filter === segment.key} on:click={() => (filter = segment.key)}>
              {segment.label}<span>{segment.count}</span>
            </button>
          {/each}
        </div>
      </div>
      {#if visible.length}
        <ul class="zo__list">
          {#each visible as row (row.id)}
            <li>
              <button type="button" on:click={() => onOpenEndpoint?.(row.id)}>
                <i class={`bi ${row.dfs ? 'bi-diagram-3' : 'bi-hdd-network'}`} aria-hidden="true"></i>
                <span class="zo__name"><strong>{row.ep?.name ?? '—'}</strong><small class="mono">{row.ep?.host ?? ''}</small></span>
                <span class="zo__folders" class:warn={row.toReview > 0}>{foldersLabel(row)}</span>
                <span><span class={`zo__pill zo__pill--${row.state.tone}`}>{row.state.label}</span></span>
                <span class="zo__when">{row.dfs ? '' : lastTest(row.ep)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="zo__empty">{t('No server matches this search.')}</p>
      {/if}
    {:else}
      <p class="zo__empty">{t('No server in this zone yet: add a file server or a DFS namespace.')}</p>
    {/if}
  </section>

  <aside class="zo__side" aria-label={t('Governance')}>
    <h2>{t('Governance')}</h2>
    <dl>
      <div><dt>{t('OU of the groups')}</dt><dd class="mono">{provisioningOu || t('Not set')}</dd></div>
      <div>
        <dt>{t('Naming')}</dt>
        <dd>
          <span class="mono">{namingTemplateLabel || t('Not set')}</span>
          {#if onOpenProvisioning}<button type="button" class="zo__link" on:click={() => onOpenProvisioning?.()}>{t('Edit in Provisioning')} ›</button>{/if}
        </dd>
      </div>
      {#if lastChange?.at}
        <div><dt>{t('Last change')}</dt><dd>{lastChange.actor ?? '—'}<small>{formatDateTime(lastChange.at)}</small></dd></div>
      {/if}
    </dl>
  </aside>
</div>

<style>
  .zo {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: 28px;
    align-items: start;
  }

  .zo__main {
    min-width: 0;
  }

  .zo__tools {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
  }

  .zo__tools .b2s-input {
    flex: 1;
    max-width: 280px;
  }

  .zo__seg {
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface-muted, #e9ebf0);
  }

  .zo__seg button {
    border: 0;
    background: none;
    border-radius: var(--b2s-radius-sm);
    padding: 4px 10px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
    cursor: pointer;
  }

  .zo__seg button.on {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 600;
  }

  .zo__seg span {
    margin-left: 5px;
    opacity: 0.7;
  }

  .zo__list {
    margin: 0;
    padding: 0;
    list-style: none;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .zo__list li + li {
    border-top: 1px solid var(--b2s-color-border);
  }

  .zo__list button {
    display: grid;
    grid-template-columns: 20px minmax(0, 1.2fr) minmax(0, 1fr) 120px 130px;
    gap: 12px;
    align-items: center;
    width: 100%;
    padding: 10px 12px;
    border: 0;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .zo__list button:hover {
    background: var(--b2s-color-surface-muted, #f6f7f9);
  }

  .zo__list i {
    color: var(--b2s-color-text-muted);
  }

  .zo__name {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .zo__name strong {
    font-weight: 500;
  }

  .zo__name small,
  .zo__when,
  .zo__folders {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .zo__name small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .zo__folders.warn {
    color: var(--b2s-color-warning-strong, #a85a00);
  }

  .zo__pill {
    display: inline-flex;
    padding: 2px 9px;
    border-radius: 99px;
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
    white-space: nowrap;
  }

  .zo__pill--ok { background: var(--b2s-color-success-soft, #ddf5e9); color: var(--b2s-color-success, #0b7a4b); }
  .zo__pill--bad { background: var(--b2s-color-danger-soft, #fce6e6); color: var(--b2s-color-danger, #c22f2f); }
  .zo__pill--r { background: var(--b2s-color-info-soft, #e4edfd); color: var(--b2s-color-info, #1f5fd0); }
  .zo__pill--n { background: var(--b2s-color-surface-muted, #e9ebf0); color: var(--b2s-color-text-muted); }

  .zo__empty {
    margin: 0;
    padding: 16px;
    border: 1px dashed var(--b2s-color-border);
    border-radius: var(--b2s-radius-md);
    color: var(--b2s-color-text-muted);
    text-align: center;
  }

  .zo__side h2 {
    margin: 0 0 6px;
    font-size: var(--b2s-fs-xs);
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--b2s-color-text-muted);
    font-weight: 600;
  }

  .zo__side dl {
    margin: 0;
  }

  .zo__side dl div {
    display: grid;
    grid-template-columns: 105px minmax(0, 1fr);
    gap: 8px;
    padding: 9px 0;
    border-top: 1px solid var(--b2s-color-border);
    font-size: var(--b2s-fs-sm);
  }

  .zo__side dl div:first-child {
    border-top: 0;
  }

  .zo__side dt {
    color: var(--b2s-color-text-muted);
  }

  .zo__side dd {
    margin: 0;
    display: flex;
    flex-direction: column;
    overflow-wrap: anywhere;
  }

  .zo__side dd small {
    color: var(--b2s-color-text-muted);
  }

  .zo__link {
    align-self: flex-start;
    margin-top: 2px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--b2s-color-info);
    font-size: var(--b2s-fs-sm);
    text-align: left;
    cursor: pointer;
  }

  .mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-sm);
  }
</style>
