<script lang="ts">
  import { page } from '$app/stores';
  import { apiGetData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { formatBytes, formatDate, formatDateTime } from '$lib/utils/format';

  /**
   * One report, the same layout for all: key figures, then tables. Printed (or saved as PDF) without the
   * navigation, with its date and its scope on each page; a folder links to its page on screen.
   */
  type Column = { key: string; label: string; type: 'text' | 'folder' | 'bytes' | 'percent' | 'int' | 'date' | 'status' | 'score' };
  type Section = { title: string; description?: string; columns: Column[]; rows: Array<Record<string, any>>; empty?: string };
  type Kpi = { label: string; value: number | null; type: Column['type']; hint?: string | null; tone?: string | null };
  type Report = { key: string; title: string; description: string; generated_at: string; scope: string; kpis: Kpi[]; sections: Section[];
    zones: Array<{ id: number; name: string }> };

  let report: Report | null = null;
  let error = '';
  let zoneId = 0;
  let loadedFor = '';
  $: kind = $page.params.kind;
  $: key = `${kind}:${zoneId}`;
  $: if (kind && key !== loadedFor) load();
  async function load() {
    loadedFor = key;
    error = '';
    try {
      report = await apiGetData<Report>(fetch, `/insights/reports/${kind}`, zoneId ? { zone_id: zoneId } : undefined);
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
    return /retard|plein|non demandée/.test(text) ? 'bad' : /surveiller|en cours/.test(text) ? 'warn' : /ok|corrigée/.test(text) ? 'ok' : '';
  };
</script>

<section class="b2s-page b2s-page--admin rv">
  <nav class="rv__crumbs no-print"><a href="/reports"><i class="bi bi-arrow-left" aria-hidden="true"></i> {t('All the reports')}</a></nav>
  {#if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !report}
    <LoadingState block skeleton="detail" />
  {:else}
    <header class="rv__head">
      <div>
        <span class="rv__brand">BornToShare · {t('Report')}</span>
        <h1>{report.title}</h1>
        <p>{report.description}</p>
        <small>{report.scope} · {t('generated on {date}', { date: formatDateTime(report.generated_at) })}</small>
      </div>
      <div class="rv__tools no-print">
        {#if report.zones?.length}
          <select class="b2s-input" bind:value={zoneId} aria-label={t('Zone')}>
            <option value={0}>{t('All the zones')}</option>
            {#each report.zones as zone (zone.id)}<option value={zone.id}>{zone.name}</option>{/each}
          </select>
        {/if}
        <button type="button" class="b2s-btn b2s-btn-primary" on:click={() => window.print()}>
          <i class="bi bi-printer" aria-hidden="true"></i>{t('Print or save as PDF')}</button>
      </div>
    </header>

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

<style>
  .rv { display: flex; flex-direction: column; gap: 20px; padding: var(--b2s-page-padding, 24px 28px); }
  .rv__crumbs a { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .rv__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .rv__brand { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
  .rv__head h1 { margin: 2px 0 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 650; }
  .rv__head p { margin: 4px 0; color: var(--b2s-color-text-muted); }
  .rv__head small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rv__tools { display: flex; gap: 10px; align-items: center; }
  .rv__tools select { width: 200px; }
  .rv__tools .b2s-btn i { margin-right: 6px; }
  .rv__kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
  .rv__kpi { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .rv__kpi span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .rv__kpi b { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .rv__kpi small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .is-ok { color: var(--b2s-color-success-strong, #1a7f37); }
  .is-warn { color: var(--b2s-color-warning-strong, #9a5b00); }
  .is-bad { color: var(--b2s-color-danger-strong, #b42318); }
  .rv__section { padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); break-inside: avoid-page; }
  .rv__section h2 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: var(--b2s-fs-md); font-weight: 600; }
  .rv__section h2 small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .rv__desc { margin: -4px 0 8px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  table { width: 100%; border-collapse: collapse; font-size: var(--b2s-fs-sm); }
  th { padding: 6px 8px; border-bottom: 1px solid var(--b2s-color-border-strong, #cfd6e0); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-align: left; text-transform: uppercase; letter-spacing: 0.03em; }
  td { padding: 7px 8px; border-bottom: 1px solid var(--b2s-color-border); vertical-align: top; }
  tr { break-inside: avoid; }
  th.is-bytes, th.is-percent, th.is-int, td.is-bytes, td.is-percent, td.is-int { text-align: right; font-variant-numeric: tabular-nums; }
  th.is-score, td.is-score { text-align: center; }
  td.is-folder a { color: inherit; text-decoration: none; }
  td.is-folder small { display: block; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro, 11px); }
  .rv__pill { display: inline-block; min-width: 34px; padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); font-size: var(--b2s-fs-xs); font-weight: 600; text-align: center; }
  .rv__pill.is-ok { background: var(--b2s-color-success-soft, #eaf7ee); color: var(--b2s-color-success-strong, #1a7f37); }
  .rv__pill.is-warn { background: var(--b2s-color-warning-soft, #fff4e5); color: var(--b2s-color-warning-strong, #9a5b00); }
  .rv__pill.is-bad { background: var(--b2s-color-danger-soft, #fdecea); color: var(--b2s-color-danger-strong, #b42318); }
  .rv__empty { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }

  /* Printed: no navigation, no tools, white paper, tables kept whole when they fit */
  @media print {
    :global(.sb), :global(.b2s-toaster), :global(.b2s-banner), .no-print { display: none !important; }
    :global(.b2s-app-root) { display: block !important; }
    :global(.b2s-app-main) { padding: 0 !important; margin: 0 !important; }
    :global(body) { background: #fff !important; }
    .rv { gap: 12px; }
    .rv__section, .rv__kpi { border-color: #d0d5dd; box-shadow: none; }
    td.is-folder a { color: #000; }
  }
</style>
