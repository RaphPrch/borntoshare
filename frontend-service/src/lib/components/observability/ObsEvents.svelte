<script lang="ts">
  

  import { recall, remember } from '$lib/utils/remember';
  import { onDestroy, onMount, untrack } from 'svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
  import { toast } from '$lib/stores/toast';
  import { copyText } from '$lib/utils/clipboard';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { formatActivityItem } from '$lib/activity/format';
  import { reportUiError } from '$lib/errors';
  import { searchEvents, type EventSearch, type ObsPeriod } from '$lib/api/observability';
  import type { StatusVariant } from '$lib/utils/status';

  
  interface Props {
    period?: ObsPeriod;
    /** Opened from the overview: « failure » shows the refused sign-ins and other failures */
    initialOutcome?: '' | 'success' | 'failure';
    initialModule?: string;
  }

  let { period = '24h', initialOutcome = '', initialModule = '' }: Props = $props();

  let items: Record<string, unknown>[] = $state([]);
  let total = $state(0);
  let modules: string[] = $state([]);
  let page = $state(1);
  let pageSize = $state(recall('events', { pageSize: 50 }).pageSize);
  $effect.pre(() => {
    remember('events', { pageSize });
  });
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let module = $state(initialModule);
  let severity = $state('');
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let outcome: '' | 'success' | 'failure' = $state(initialOutcome);
  let actor = $state('');
  let query = $state('');
  let loading = $state(true);
  let loadError: string | null = $state(null);
  let debounce: ReturnType<typeof setTimeout> | null = null;
  let mounted = $state(false);
  let requestSeq = 0;

  const MODULE_LABELS: Record<string, () => string> = {
    auth: () => t('Sign-in'),
    access_request: () => t('Access requests'),
    identity: () => t('Identities'),
    identity_source: () => t('Identity sources'),
    infrastructure: () => t('Infrastructure'),
    logs: () => t('Logs'),
    storage_endpoint: () => t('Storage endpoints'),
    storage_root: () => t('Storage roots'),
    tag: () => t('Tags'),
    zone: () => t('Zones'),
    naming_policy: () => t('Naming policy'),
    provisioning_job: () => t('Jobs')
  };
  const moduleLabel = (key: string) => MODULE_LABELS[key]?.() ?? key.replace(/_/g, ' ');

  function params(p = page, size = pageSize): EventSearch {
    return { page: p, page_size: size, period, module, severity, outcome, actor: actor.trim(), q: query.trim() };
  }

  async function load() {
    const seq = ++requestSeq;
    loading = true;
    loadError = null;
    try {
      const result = await searchEvents(fetch, params());
      if (seq !== requestSeq) return;
      items = result.items;
      total = result.total;
      if (result.modules.length) modules = result.modules;
    } catch (error: unknown) {
      if (seq === requestSeq) loadError = reportUiError(error, t('Unable to load the events.'), 'observability.events.load');
    } finally {
      if (seq === requestSeq) loading = false;
    }
  }

  /** Filters reset to the first page; typing waits a little before asking the server */
  function refilter(wait = 0) {
    if (!mounted) return;
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(() => {
      if (page !== 1) page = 1;
      else void load();
    }, wait);
  }

  $effect.pre(() => {
    void [period, module, severity, outcome]; // only these start it again (as the former « $: »)
    untrack(() => { refilter(0); });
  });
  $effect.pre(() => {
    void [actor, query]; // only these start it again (as the former « $: »)
    untrack(() => { refilter(350); });
  });
  $effect.pre(() => {
    void [page, pageSize, mounted]; // only these start it again (as the former « $: »)
    untrack(() => { mounted && void load(); });
  });

  onMount(() => {
    mounted = true;
  });
  onDestroy(() => {
    if (debounce) clearTimeout(debounce);
  });

  const outcomeOf = (entry: Record<string, unknown>) => String(entry.outcome ?? '').toLowerCase();
  const failed = (entry: Record<string, unknown>) => ['failure', 'failed', 'error'].includes(outcomeOf(entry));

  function badge(entry: Record<string, unknown>): { label: string; variant: StatusVariant } {
    const sev = String(entry.severity ?? '').toLowerCase();
    if (failed(entry) || ['critical', 'error', 'high'].includes(sev)) return { label: failed(entry) ? t('Failure') : t('Error'), variant: 'error' };
    if (sev === 'warning') return { label: t('Warning'), variant: 'warning' };
    return { label: t('Success'), variant: 'success' };
  }

  function row(entry: Record<string, unknown>) {
    const rendered = formatActivityItem(entry as never);
    const action = String(entry.action ?? '');
    return {
      id: String(entry.id ?? ''),
      at: entry.created_at as string,
      module: moduleLabel(action.includes('.') ? action.split('.')[0] : 'platform'),
      moduleKey: action.includes('.') ? action.split('.')[0] : '',
      action,
      actorName: String(entry.actor_display ?? ''),
      raw: entry,
      title: rendered?.title || action,
      details: rendered?.subtitle1 || '',
      actor: String(entry.actor_display ?? (entry.actor_type === 'system' ? t('System') : '—')),
      target: String(entry.target_display ?? ''),
      badge: badge(entry)
    };
  }

  let rows = $derived(items.map(row));
  type Row = (typeof rows)[number];

  // ---- right click on an event, and its detail ----
  let menu = $state<{ row: Row; at: { x: number; y: number } } | null>(null);
  let detail = $state<Row | null>(null);
  const menuItems = (r: Row): ContextMenuItem[] => [
    { key: 'detail', label: t('See the detail'), icon: 'bi-card-text' },
    { key: 'actor', label: t('Only this actor'), icon: 'bi-person', separated: true, disabled: !r.actorName },
    { key: 'module', label: t('Only this kind of event ({name})', { name: r.module }), icon: 'bi-funnel', disabled: !r.moduleKey || !modules.includes(r.moduleKey) },
    { key: 'target', label: t('Search this target'), icon: 'bi-search', disabled: !r.target },
    { key: 'copy', label: t('Copy the event'), icon: 'bi-clipboard', separated: true }
  ];
  async function pick(key: string) {
    const r = menu?.row;
    menu = null;
    if (!r) return;
    if (key === 'detail') detail = r;
    else if (key === 'actor') actor = r.actorName;
    else if (key === 'module') module = r.moduleKey;
    else if (key === 'target') query = r.target;
    else if (key === 'copy') {
      const text = `${formatDateTime(r.at)} · ${r.title}${r.details ? ` · ${r.details}` : ''} · ${r.actor}${r.target ? ` · ${r.target}` : ''}`;
      if (await copyText(text)) toast.success(t('Event copied.'));
    }
  }

  let exporting = $state(false);
  async function exportCsv() {
    exporting = true;
    try {
      const all: Record<string, unknown>[] = [];
      for (let p = 1; p <= 10; p += 1) {
        const result = await searchEvents(fetch, params(p, 200));
        all.push(...result.items);
        if (all.length >= result.total || result.items.length < 200) break;
      }
      const data = all.map(row);
      downloadCsv(csvFilename('events'), [
        { header: t('Date'), value: (r: (typeof data)[number]) => formatDateTime(r.at) },
        { header: t('Module'), value: (r: (typeof data)[number]) => r.module },
        { header: t('Result'), value: (r: (typeof data)[number]) => r.badge.label },
        { header: t('Event'), value: (r: (typeof data)[number]) => r.title },
        { header: t('Actor'), value: (r: (typeof data)[number]) => r.actor },
        { header: t('Target'), value: (r: (typeof data)[number]) => r.target },
        { header: t('Details'), value: (r: (typeof data)[number]) => r.details }
      ], data);
    } catch (error: unknown) {
      reportUiError(error, t('Export failed.'), 'observability.events.export');
    } finally {
      exporting = false;
    }
  }
</script>

<div class="obs-events">
  <div class="b2s-toolbar">
    <SearchField wrapperClass="b2s-toolbar__search" placeholder={t('Search an event, a target…')} ariaLabel={t('Search events')} bind:value={query} />
    <select class="b2s-select" bind:value={module} aria-label={t('Module')}>
      <option value="">{t('All modules')}</option>
      {#each modules as key (key)}<option value={key}>{moduleLabel(key)}</option>{/each}
    </select>
    <select class="b2s-select" bind:value={outcome} aria-label={t('Result')}>
      <option value="">{t('All results')}</option>
      <option value="success">{t('Success')}</option>
      <option value="failure">{t('Failure')}</option>
    </select>
    <select class="b2s-select" bind:value={severity} aria-label={t('Severity')}>
      <option value="">{t('All severities')}</option>
      <option value="info">{t('Info')}</option>
      <option value="warning">{t('Warning')}</option>
      <option value="critical">{t('Critical')}</option>
    </select>
    <input class="obs-actor" bind:value={actor} placeholder={t('Actor')} aria-label={t('Actor')} />
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-toolbar__end" onclick={exportCsv} disabled={exporting || total === 0}>
      <i class={`bi ${exporting ? 'bi-hourglass-split' : 'bi-download'}`} aria-hidden="true"></i>{t('Export CSV')}
    </button>
  </div>

  {#if loadError}
    <InlineAlert tone="error">{loadError}</InlineAlert>
  {/if}

  <section class="b2s-card obs-card">
    {#if loading && rows.length === 0}
      <LoadingState skeleton="rows" />
    {:else if rows.length === 0}
      <EmptyStateInline message={t('No event matches these filters.')} />
    {:else}
      <div class="b2s-table-wrap" class:is-loading={loading}>
        <table class="b2s-table obs-table">
          <thead>
            <tr>
              <th class="col-date">{t('Date')}</th>
              <th class="col-result">{t('Result')}</th>
              <th>{t('Event')}</th>
              <th class="col-actor">{t('Actor')}</th>
            </tr>
          </thead>
          <tbody>
            {#each rows as r (r.id)}
              <tr class="obs-row" oncontextmenu={(event) => { event.preventDefault(); menu = { row: r, at: menuPositionFor(event) }; }} ondblclick={() => (detail = r)}>
                <td class="col-date">
                  <span>{formatDateTime(r.at)}</span>
                  <small>{r.module}</small>
                </td>
                <td><StatusBadge compact variant={r.badge.variant} label={r.badge.label} /></td>
                <td class="obs-main">
                  <strong>{r.title}</strong>
                  {#if r.details}<small>{r.details}</small>{/if}
                </td>
                <td class="col-actor" title={r.actor}>{r.actor}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <Pagination {total} bind:page bind:pageSize pageSizes={[25, 50, 100, 200]} />
    {/if}
  </section>
</div>

<ContextMenu open={Boolean(menu)} title={menu?.row.title ?? ''} subtitle={menu ? formatDateTime(menu.row.at) : ''} items={menu ? menuItems(menu.row) : []}
  at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={(key) => void pick(key)} />

<Drawer open={Boolean(detail)} title={detail?.title ?? ''} subtitle={detail ? formatDateTime(detail.at) : ''} iconClass="bi-card-text" onClose={() => (detail = null)}>
  {#if detail}
    <dl class="obs-detail">
      <dt>{t('Result')}</dt><dd>{detail.badge.label}</dd>
      <dt>{t('Actor')}</dt><dd>{detail.actor}</dd>
      <dt>{t('Target')}</dt><dd>{detail.target || '—'}</dd>
      <dt>{t('Event')}</dt><dd><code>{detail.action}</code></dd>
      {#if detail.details}<dt>{t('Detail')}</dt><dd>{detail.details}</dd>{/if}
    </dl>
    <pre class="obs-json">{JSON.stringify((detail.raw as any)?.context_json ?? (detail.raw as any)?.metadata ?? {}, null, 2)}</pre>
  {/if}
</Drawer>

<style>
  .obs-row { cursor: context-menu; }
  .obs-detail { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0 0 12px; font-size: var(--b2s-fs-sm); }
  .obs-detail dt { color: var(--b2s-color-text-muted); }
  .obs-detail dd { margin: 0; overflow-wrap: anywhere; }
  .obs-json { max-height: 360px; overflow: auto; margin: 0; padding: 10px 12px; border-radius: 10px; background: var(--b2s-color-surface-muted); font-size: 12px; white-space: pre-wrap; }
  .obs-events {
    display: grid;
    gap: 16px;
  }

  .obs-card {
    overflow: hidden;
  }

  .obs-actor {
    height: 38px;
    width: 160px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
  }

  .is-loading {
    opacity: 0.6;
  }

  .obs-table .col-date {
    width: 170px;
    white-space: nowrap;
  }

  .col-date span,
  .col-date small {
    display: block;
  }

  .col-date small,
  .obs-main small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .col-result {
    width: 120px;
  }

  .obs-main strong {
    display: block;
    font-weight: 600;
  }

  .obs-main small {
    display: block;
    margin-top: 2px;
  }

  .col-actor {
    width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
