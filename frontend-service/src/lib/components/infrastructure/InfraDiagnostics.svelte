<script lang="ts">
  // Diagnostic of the installation (Observability › Health): run by the core on demand, problems first, each with
  // what it means and what to do; exported as CSV for a support request. Read only, never a secret.
  import { t } from '$lib/i18n';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { reportUiError } from '$lib/errors';
  import { timeAgo } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { RESULT_VARIANT, describeCheck, resultLabel, severityLabel, sortChecks } from '$lib/utils/diagnostics';
  import { getDiagnostics, type DiagnosticCheck, type DiagnosticReport } from '$lib/api/infrastructure';

  let report = $state<DiagnosticReport | null>(null);
  let running = $state(false);

  let rows = $derived(sortChecks(report?.checks ?? []).map((check) => ({ check, ...describeCheck(check) })));
  let problems = $derived(rows.filter((row) => row.check.result !== 'ok'));

  async function run() {
    running = true;
    try {
      report = await getDiagnostics(fetch);
    } catch (e) {
      reportUiError(e, t('Unable to run the diagnostic.'), 'observability.diagnostics');
    } finally {
      running = false;
    }
  }

  function exportCsv() {
    downloadCsv(csvFilename('borntoshare-diagnostic'), [
      { header: t('Checked item'), value: (row: (typeof rows)[number]) => row.title },
      { header: t('Result'), value: (row) => resultLabel(row.check.result) },
      { header: t('Severity'), value: (row) => (row.check.result === 'ok' ? '' : severityLabel(row.check.severity)) },
      { header: t('Explanation'), value: (row) => row.detail },
      { header: t('What to do'), value: (row) => row.action ?? '' }
    ], rows);
  }

  const severityTone = (check: DiagnosticCheck) => (check.severity === 'critical' || check.severity === 'high' ? 'bad' : 'warn');
</script>

<section class="v2-sec diag">
  <div class="v2-sh">
    <h2>{t('Diagnostic')}</h2>
    {#if report}
      <span class="v2-hint">{t('Run {ago}', { ago: timeAgo(report.generated_at) })} · {t('{problems} problem(s) out of {total} checks', { problems: problems.length, total: report.summary.total })}</span>
    {/if}
    <div class="v2-sh__r">
      {#if report}
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={exportCsv}>
          <i class="bi bi-download" aria-hidden="true"></i>{t('Export')}
        </button>
      {/if}
      <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={run} disabled={running}>
        <i class={`bi ${running ? 'bi-hourglass-split' : 'bi-clipboard2-pulse'}`} aria-hidden="true"></i>
        {running ? t('Checking…') : report ? t('Run again') : t('Run the diagnostic')}
      </button>
    </div>
  </div>

  {#if running && !report}
    <LoadingState block skeleton="rows">{t('Running the diagnostic…')}</LoadingState>
  {:else if !report}
    <p class="v2-hint">{t('Configuration, databases, job queue, disk, workers, directories, file servers and modules, checked now, with what to do for each problem.')}</p>
  {:else}
    <div class="v2-list" role="table" aria-label={t('Diagnostic')}>
      <div class="v2-row is-head diag__row" role="row">
        <span role="columnheader">{t('Checked item')}</span><span role="columnheader">{t('Result')}</span><span role="columnheader">{t('Explanation')}</span>
      </div>
      {#each rows as row (row.check.code)}
        <div class="v2-row diag__row" role="row">
          <span role="cell" class="diag__title">{row.title}</span>
          <span role="cell" class="diag__result">
            <StatusBadge variant={RESULT_VARIANT[row.check.result]} compact showDot label={resultLabel(row.check.result)} />
            {#if row.check.result !== 'ok' && row.check.result !== 'unknown'}
              <span class={`v2-tag is-${severityTone(row.check)}`}>{severityLabel(row.check.severity)}</span>
            {/if}
          </span>
          <span role="cell" class="diag__detail">
            {row.detail}
            {#if row.action}<small><i class="bi bi-arrow-return-right" aria-hidden="true"></i> {row.action}</small>{/if}
          </span>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .diag { margin-top: 20px; }
  .diag__row { grid-template-columns: minmax(180px, 1fr) 250px minmax(0, 2.4fr); align-items: start; }
  .diag__title { font-weight: 600; color: var(--b2s-color-heading); }
  .diag__result { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .diag__detail { display: flex; flex-direction: column; gap: 4px; color: var(--b2s-color-text); overflow-wrap: anywhere; }
  .diag__detail small { color: var(--b2s-color-text-soft); }
</style>
