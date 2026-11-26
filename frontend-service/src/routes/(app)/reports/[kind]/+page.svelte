<script lang="ts">
  import { untrack } from 'svelte';

  import { page } from '$app/stores';
  import { apiGetData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import FivesOffNotice from '$lib/components/settings/FivesOffNotice.svelte';
  import { t } from '$lib/i18n';
  import { formatBytes, formatDate, formatDateTime } from '$lib/utils/format';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import { STATE_LABELS } from '$lib/components/storage-roots/folder-query';

  /**
   * One report, the same layout for all: key figures, then tables. Printed (or saved as PDF) without the
   * navigation, with its date and its scope on each page; a folder links to its page on screen.
   */
  type Column = { key: string; label: string; type: 'text' | 'folder' | 'bytes' | 'percent' | 'int' | 'date' | 'status' | 'score' };
  type Section = { title: string; description?: string; columns: Column[]; rows: Array<Record<string, any>>; empty?: string };
  type Kpi = { label: string; value: number | null; type: Column['type']; hint?: string | null; tone?: string | null };
  type Report = { key: string; title: string; description: string; generated_at: string; scope: string; kpis: Kpi[]; sections: Section[];
    zones: Array<{ id: number; name: string }>; servers?: Array<{ id: number; name: string }>; tags?: string[]; period_days?: number };

  let report = $state<Report | null>(null);
  let error = $state('');
  let zoneId = $state(0);
  // The filters of the report: the folders it reads (the same « est:… » search as Storage Roots), the period of the requests
  let serverId = $state(0);
  let tag = $state('');
  let stateKey = $state('');
  let query = $state('');
  let applied = $state('');
  let days = $state(30);
  let search = $derived([stateKey ? `est:${stateKey}` : '', applied].filter(Boolean).join(' '));
  let loadedFor = $state('');
  async function load() {
    loadedFor = key;
    error = '';
    try {
      // fives-…: a report of the 5S module (its own service)
      const base = kind.startsWith('fives-') ? '/modules/fives/reports' : '/insights/reports';
      // The 5S module filters by zone; the core by zone, server, tag, search and period
      const params: Record<string, string | number> = zoneId ? { zone_id: zoneId } : {};
      if (!kind.startsWith('fives-')) {
        if (serverId) params.server_id = serverId;
        if (tag) params.tag = tag;
        if (search) params.q = search;
        if (kind === 'requests') params.days = days;
      }
      report = await apiGetData<Report>(fetch, `${base}/${kind}`, Object.keys(params).length ? params : undefined);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the report.');
    }
  }

  function show(value: any, type: Column['type']): string {
    if (value == null || value === '') return '—';
    switch (type) {
      case 'bytes': return formatBytes(Number(value));
      case 'percent': return `${Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
      case 'int': return Number(value).toLocaleString('fr-FR');
      case 'score': return String(value);
      case 'date': return formatDate(value);
      default: return String(value);
    }
  }
  const scoreTone = (value: any) => (value == null ? '' : Number(value) >= 80 ? 'ok' : Number(value) >= 60 ? 'warn' : 'bad');
  const statusTone = (value: any) => {
    const text = String(value ?? '');
    return /retard|plein|non demandée|critique|élevée/.test(text) ? 'bad' : /surveiller|en cours|avertissement/.test(text) ? 'warn' : /ok|corrigée/.test(text) ? 'ok' : '';
  };
  let kind = $derived($page.params.kind);
  // A report of the 5S module while the module is not usable: said, and the module is not called
  let fivesOff = $derived(($page.data as { fivesOff?: { reason: string } | null }).fivesOff ?? null);
  let key = $derived(`${kind}:${zoneId}:${serverId}:${tag}:${search}:${days}`);
  let core = $derived(!kind.startsWith('fives-'));
  let filtered = $derived(Boolean(zoneId || serverId || tag || search));
  function reset() {
    zoneId = 0; serverId = 0; tag = ''; stateKey = ''; query = ''; applied = '';
  }
  $effect.pre(() => {
    if (kind && !fivesOff && key !== loadedFor) untrack(load);
  });
</script>

{#if fivesOff}
  <FivesOffNotice reason={fivesOff.reason} />
{:else}
<section class="b2s-page b2s-page--admin rv">
  <nav class="rv__crumbs no-print"><a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href="/reports"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the reports')}</a></nav>
  {#if error}<InlineAlert tone="error">{error}</InlineAlert>{/if}
  {#if !report}
    {#if !error}<LoadingState block skeleton="detail" />{/if}
  {:else}
    <header class="rv__head">
      <div>
        <span class="rv__brand">BornToShare · {t('Report')}</span>
        <h1>{report.title}</h1>
        <p>{report.description}</p>
        <small>{report.scope} · {t('generated on {date}', { date: formatDateTime(report.generated_at) })}</small>
      </div>
      <div class="rv__tools no-print">
        <button type="button" class="b2s-btn b2s-btn-primary" onclick={() => window.print()}>
          <i class="bi bi-printer" aria-hidden="true"></i>{t('Print or save as PDF')}</button>
      </div>
    </header>

    <div class="rv__filters no-print" aria-label={t('Filters of the report')}>
      {#if report.zones?.length}
        <select class="b2s-input" bind:value={zoneId} onchange={() => (serverId = 0)} aria-label={t('Zone')}>
          <option value={0}>{t('All the zones')}</option>
          {#each report.zones as zone (zone.id)}<option value={zone.id}>{zone.name}</option>{/each}
        </select>
      {/if}
      {#if core}
        {#if report.servers?.length}
          <select class="b2s-input" bind:value={serverId} aria-label={t('Server')}>
            <option value={0}>{t('All the servers')}</option>
            {#each report.servers as server (server.id)}<option value={server.id}>{server.name}</option>{/each}
          </select>
        {/if}
        {#if report.tags?.length}
          <select class="b2s-input" bind:value={tag} aria-label={t('Tag')}>
            <option value="">{t('All the tags')}</option>
            {#each report.tags as name (name)}<option value={name}>{name}</option>{/each}
          </select>
        {/if}
        <select class="b2s-input" bind:value={stateKey} aria-label={t('State')}>
          <option value="">{t('Every state')}</option>
          {#each STATE_LABELS().filter(([key]) => key !== 'tous') as [key, label] (key)}<option value={key}>{label}</option>{/each}
        </select>
        {#if kind === 'requests'}
          <select class="b2s-input" bind:value={days} aria-label={t('Period')}>
            {#each [7, 30, 90, 365] as value (value)}<option value={value}>{t('{n} days', { n: value })}</option>{/each}
          </select>
        {/if}
        <SearchField bind:value={query} placeholder={t('Search: tag:Finance gardien:alice taille>1Go…')} ariaLabel={t('Search the folders')}
          wrapperClass="rv__search" onEnter={() => (applied = query.trim())} />
      {/if}
      {#if filtered}<button type="button" class="b2s-link-btn" onclick={reset}>{t('Clear the filters')}</button>{/if}
    </div>

    <div class="rv__kpis">
      {#each report.kpis as kpi (kpi.label)}
        <div class="rv__kpi">
          <span>{kpi.label}</span>
          <b class={kpi.type === 'score' ? `is-${scoreTone(kpi.value)}` : kpi.tone ? `is-${kpi.tone}` : ''}>{show(kpi.value, kpi.type)}</b>
          {#if kpi.hint}<small>{kpi.hint}</small>{/if}
        </div>
      {/each}
    </div>

    {#each report.sections as section (section.title)}
      <section class="rv__section">
        <h2>{section.title} <small>{section.rows.length}</small></h2>
        {#if section.description}<p class="rv__desc">{section.description}</p>{/if}
        {#if section.rows.length}
          <table>
            <thead><tr>{#each section.columns as column (column.key)}<th class={`is-${column.type}`}>{column.label}</th>{/each}</tr></thead>
            <tbody>
              {#each section.rows as row, index (index)}
                <tr>
                  {#each section.columns as column (column.key)}
                    <td class={`is-${column.type}`}>
                      {#if column.type === 'folder'}
                        <a href={`/storage-roots?selected=${row[column.key]?.id}`}><b>{row[column.key]?.name ?? '—'}</b></a>
                        <small>{row[column.key]?.path ?? ''}</small>
                      {:else if column.type === 'score'}
                        <span class={`rv__pill is-${scoreTone(row[column.key])}`}>{show(row[column.key], 'score')}</span>
                      {:else if column.type === 'status'}
                        <span class={`rv__pill is-${statusTone(row[column.key])}`}>{show(row[column.key], 'text')}</span>
                      {:else}
                        {show(row[column.key], column.type)}
                      {/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="rv__empty">{section.empty ?? t('Nothing to report.')}</p>
        {/if}
      </section>
    {/each}
  {/if}
</section>
{/if}

<style>
  .rv { display: flex; flex-direction: column; gap: 20px; padding: var(--b2s-page-padding, 24px 28px); }
  .rv__crumbs a { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .rv__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .rv__brand { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
  .rv__head h1 { margin: 2px 0 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 650; }
  .rv__head p { margin: 4px 0; color: var(--b2s-color-text-muted); }
  .rv__head small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rv__tools { display: flex; gap: 10px; align-items: center; }
  .rv__filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .rv__filters select { width: auto; min-width: 150px; max-width: 220px; }
  .rv__filters :global(.rv__search) { flex: 1 1 260px; }
  .rv__tools .b2s-btn i { margin-right: 6px; }
  .rv__kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
  .rv__kpi { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .rv__kpi span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .rv__kpi b { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .rv__kpi small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .is-ok { color: var(--b2s-color-success-strong); }
  .is-warn { color: var(--b2s-color-warning-strong); }
  .is-bad { color: var(--b2s-color-danger-strong); }
  .rv__section { padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); break-inside: avoid-page; }
  .rv__section h2 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: var(--b2s-fs-md); font-weight: 600; }
  .rv__section h2 small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .rv__desc { margin: -4px 0 8px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  table { width: 100%; border-collapse: collapse; font-size: var(--b2s-fs-sm); }
  th { padding: 6px 8px; border-bottom: 1px solid var(--b2s-color-border-strong); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-align: left; text-transform: uppercase; letter-spacing: 0.03em; }
  td { padding: 7px 8px; border-bottom: 1px solid var(--b2s-color-border); vertical-align: top; }
  tr { break-inside: avoid; }
  th.is-bytes, th.is-percent, th.is-int, td.is-bytes, td.is-percent, td.is-int { text-align: right; font-variant-numeric: tabular-nums; }
  th.is-score, td.is-score { text-align: center; }
  td.is-folder a { color: inherit; text-decoration: none; }
  td.is-folder small { display: block; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro, 11px); }
  .rv__pill { display: inline-block; min-width: 34px; padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); font-size: var(--b2s-fs-xs); font-weight: 600; text-align: center; }
  .rv__pill.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .rv__pill.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .rv__pill.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .rv__empty { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }

  /* Printed: no navigation, no tools, white paper, tables kept whole when they fit */
  @media print {
    :global(.sb), :global(.b2s-toaster), :global(.b2s-banner), .no-print { display: none !important; }
    :global(.b2s-app-root) { display: block !important; }
    :global(.b2s-app-main) { padding: 0 !important; margin: 0 !important; }
    :global(body) { background: #fff !important; }
    .rv { gap: 12px; }
    .rv__section, .rv__kpi { border-color: var(--b2s-color-border); box-shadow: none; }
    td.is-folder a { color: #000; }
  }
</style>
