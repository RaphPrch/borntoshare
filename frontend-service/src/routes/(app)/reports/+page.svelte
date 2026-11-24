<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiGetData, apiGetList } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { t } from '$lib/i18n';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { formatBytes } from '$lib/utils/format';
  import { copyText } from '$lib/utils/clipboard';

  /**
   * Insights & Recommendations (v2): what the last measures, scans and ACL reads of the folders reveal, each with
   * the folders concerned one click away (the express search of Storage Roots), then the reports to print.
   */
  type Report = { key: string; title: string; description: string; source?: 'core' | 'fives' };
  type Root = Record<string, any>;
  const ICONS: Record<string, string> = { storage: 'bi-hdd-stack', security: 'bi-shield-lock', governance: 'bi-diagram-3', 'fives-5s': 'bi-stars', 'fives-hygiene': 'bi-recycle' };
  const INSIGHT_ICONS: Record<string, string> = { cold: 'bi-snow', dups: 'bi-files', secrets: 'bi-key', corrections: 'bi-tools', guardian: 'bi-person-x',
    inheritance: 'bi-scissors', quota: 'bi-speedometer2', junk: 'bi-trash3', never: 'bi-rulers' };
  let reports = $state<Report[] | null>(null);
  let roots = $state<Root[] | null>(null);
  let isAdmin = $derived(($page.data as any)?.navigation?.canSeeAdmin === true);

  onMount(async () => {
    // The reports of the core, then those of the 5S module when it is on; the folders for the recommendations
    const [core, module, rows] = await Promise.all([
      apiGetData<Report[]>(fetch, '/insights/reports').catch(() => []),
      $fivesEnabled ? apiGetData<Report[]>(fetch, '/modules/fives/reports').catch(() => []) : Promise.resolve([] as Report[]),
      apiGetList<Root>(fetch, '/storage-roots/context').catch(() => [])
    ]);
    reports = [...core, ...module];
    roots = rows;
  });

  const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
  const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);
  type Insight = { key: string; big: string; title: string; detail: string; query: string; tone: 'bad' | 'warn' | 'mut' | 'ok'; count: number };
  let insights = $derived.by(() => {
    const rows = roots ?? [];
    const list: Insight[] = [];
    const add = (insight: Insight) => insight.count > 0 && list.push(insight);
    const cold = rows.reduce((sum, row) => sum + num(row.cold_1y_bytes), 0);
    const coldFolders = rows.filter((row) => size(row) > 0 && num(row.cold_1y_bytes) > 0.5 * size(row));
    add({ key: 'cold', big: formatBytes(cold), title: t('Cold data'), tone: 'warn', count: coldFolders.length, query: 'est:donnees-froides',
      detail: t('Untouched for more than a year; {count} folder(s) are mostly cold: candidates for the archive.', { count: coldFolders.length }) });
    const dupBytes = rows.reduce((sum, row) => sum + num(row.dup_wasted_bytes) + num(row.shared_dup_bytes), 0);
    const dupFolders = rows.filter((row) => num(row.dup_wasted_bytes) + num(row.shared_dup_bytes) > 0);
    add({ key: 'dups', big: formatBytes(dupBytes), title: t('Duplicates to free'), tone: 'warn', count: dupFolders.length, query: 'est:doublons',
      detail: t('Identical files (verified fingerprint) inside or between {count} folder(s).', { count: dupFolders.length }) });
    const secrets = rows.filter((row) => num(row.password_files) + num(row.key_files) > 0);
    add({ key: 'secrets', big: String(secrets.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0)), title: t('Passwords and keys in files'),
      tone: 'bad', count: secrets.length, query: 'est:mot-de-passe', detail: t('Found by the sensitivity scan in {count} folder(s); ask their guardians to correct.', { count: secrets.length }) });
    const corrections = rows.filter((row) => ['open', 'overdue'].includes(String(row.remediation_status ?? '')));
    add({ key: 'corrections', big: String(corrections.length), title: t('Corrections in progress'), tone: 'warn', count: corrections.length, query: 'est:correction',
      detail: t('Asked to the guardians after a sensitivity scan, some may be overdue.') });
    if ($governanceEnabled) {
      const noGuardian = rows.filter((row) => num(row.guardians_count) === 0);
      add({ key: 'guardian', big: String(noGuardian.length), title: t('Folders without guardian'), tone: 'warn', count: noGuardian.length, query: 'est:sans-gardien',
        detail: t('Their requests go to the administrators.') });
      const broken = rows.filter((row) => row.inheritance_broken === true);
      add({ key: 'inheritance', big: String(broken.length), title: t('Inheritance broken'), tone: 'mut', count: broken.length, query: 'est:heritage-rompu',
        detail: t('The folder keeps its own entries and no longer follows its parent.') });
    }
    const quota = rows.filter((row) => row.quota_used_percent != null && num(row.quota_used_percent) >= num(row.quota_warn_percent ?? 85));
    add({ key: 'quota', big: String(quota.length), title: t('Quotas almost full'), tone: 'warn', count: quota.length, query: 'est:quota-plein',
      detail: t('{count} space request(s) waiting', { count: rows.reduce((sum, row) => sum + num(row.quota_pending_requests), 0) }) });
    const junk = rows.filter((row) => num(row.junk_files) > 0);
    add({ key: 'junk', big: rows.reduce((sum, row) => sum + num(row.junk_files), 0).toLocaleString('fr-FR'), title: t('Clutter files'), tone: 'mut', count: junk.length,
      query: 'est:encombre', detail: t('~$*, Thumbs.db, .tmp… in {count} folder(s): they can go.', { count: junk.length }) });
    const never = rows.filter((row) => row.content_size_bytes == null && !['done', 'running'].includes(String(row.measure_status ?? '')));
    add({ key: 'never', big: String(never.length), title: t('Folders never measured'), tone: 'mut', count: never.length, query: 'est:non-mesure',
      detail: t('No detailed volume, no 5S, no duplicates for them yet.') });
    return list;
  });
  // Share of the folders concerned by a recommendation (the bar of its card)
  let total = $derived(roots?.length ?? 0);
  const openFolders = (insight: Insight) => goto(`/storage-roots?q=${encodeURIComponent(insight.query)}`);

  // Right click on a recommendation
  let menu = $state<{ insight: Insight; at: { x: number; y: number } } | null>(null);
  let menuItems = $derived<ContextMenuItem[]>([
    { key: 'folders', label: t('See the folders concerned'), icon: 'bi-folder2-open' },
    ...(isAdmin ? [{ key: 'policy', label: t('Make a policy of it'), icon: 'bi-lightning-charge' }] : []),
    { key: 'copy', label: t('Copy the search'), icon: 'bi-clipboard', separated: true }
  ]);
  async function onPick(key: string) {
    const insight = menu?.insight;
    if (!insight) return;
    if (key === 'folders') void openFolders(insight);
    if (key === 'policy') void goto('/policies');
    if (key === 'copy') await copyText(insight.query);
  }
</script>

<section class="v2 rp">
  <div class="v2-head">
    <div>
      <h1>Insights &amp; Recommendations</h1>
      <p>{t('What the last measures, scans and ACL reads of the folders you may see reveal, and the reports to print or save as PDF.')}</p>
    </div>
  </div>

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Reports')}</h2>{#if reports?.length}<span class="v2-tag is-mut">{reports.length}</span>{/if}</div>
    {#if !reports}
      <LoadingState block skeleton="rows" rows={2} />
    {:else}
      <div class="rp__reports">
        {#each reports as report (report.key)}
          <a class="rp__report" href={`/reports/${report.key}`}>
            <span class="rp__icon"><i class={`bi ${ICONS[report.key] ?? 'bi-file-earmark-text'}`} aria-hidden="true"></i></span>
            <b>{report.title}</b>
            <small>{report.description}</small>
            <span class="rp__open">{t('Open the report')} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
          </a>
        {/each}
      </div>
    {/if}
  </div>

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Recommendations')}</h2>{#if insights.length}<span class="v2-tag is-mut">{insights.length}</span>{/if}
      <div class="v2-sh__r"><span class="v2-hint">{t('Click: the folders concerned · right click: actions')}</span></div></div>
    {#if !roots}
      <LoadingState block skeleton="rows" rows={4} />
    {:else if insights.length}
      <div class="rp__kpis">
        {#each insights as insight (insight.key)}
          {@const share = total ? Math.max(2, Math.round((insight.count / total) * 100)) : 0}
          <button type="button" class={`rp__kpi is-${insight.tone}`} onclick={() => openFolders(insight)}
            oncontextmenu={(event) => { event.preventDefault(); menu = { insight, at: menuPositionFor(event) }; }}>
            <span class="rp__kpi-head"><span class="rp__kpi-title">{insight.title}</span><i class={`bi ${INSIGHT_ICONS[insight.key] ?? 'bi-lightbulb'}`} aria-hidden="true"></i></span>
            <b class="rp__big">{insight.big}</b>
            <small>{insight.detail}</small>
            <span class="rp__share" title={t('{count} folder(s) out of {total}', { count: insight.count, total })}>
              <span class="rp__bar"><i style={`width: ${share}%`}></i></span>
              <span>{t('{count} folder(s)', { count: insight.count })} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
            </span>
          </button>
        {/each}
      </div>
    {:else}
      <p class="v2-empty">{t('Nothing to recommend')} · {t('The folders are well kept, or not measured yet.')}</p>
    {/if}
  </div>
</section>

<ContextMenu open={menu != null} title={menu?.insight.title ?? ''} subtitle={menu?.insight.query ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  /* Reports first: the kinds of report as cards */
  .rp__reports { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .rp__report { display: flex; flex-direction: column; gap: 6px; padding: 16px; border: 1px solid var(--b2s-color-border-soft); border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface-soft); color: inherit; text-decoration: none; transition: border-color var(--b2s-motion-base) var(--b2s-ease-out), box-shadow var(--b2s-motion-base) var(--b2s-ease-out), transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .rp__report:hover { border-color: var(--b2s-accent-border); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-md); transform: translateY(-1px); }
  .rp__report b { color: var(--b2s-color-heading); font-size: 15px; }
  .rp__report small { flex: 1; color: var(--b2s-color-text-muted); font-size: 12.5px; line-height: 1.45; }
  .rp__icon { display: grid; place-items: center; width: 40px; height: 40px; flex: none; margin-bottom: 4px; border-radius: 11px; background: var(--b2s-accent-soft); color: var(--b2s-accent); font-size: 19px; }
  .rp__open { color: var(--b2s-accent); font-size: 12.5px; font-weight: 600; }
  /* Recommendations as figures: value, meaning, and the share of the folders concerned */
  .rp__kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
  .rp__kpi { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px; border: 1px solid var(--b2s-color-border-soft); border-left: 3px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: border-color var(--b2s-motion-base) var(--b2s-ease-out), box-shadow var(--b2s-motion-base) var(--b2s-ease-out), transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .rp__kpi:hover { box-shadow: var(--b2s-shadow-md); transform: translateY(-1px); }
  .rp__kpi.is-bad { border-left-color: var(--b2s-color-danger); }
  .rp__kpi.is-warn { border-left-color: var(--b2s-color-warning); }
  .rp__kpi.is-mut { border-left-color: var(--b2s-color-border-strong); }
  .rp__kpi-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .rp__kpi-title { color: var(--b2s-color-text-soft); font-size: 13px; font-weight: 600; }
  .rp__kpi-head i { color: var(--b2s-color-text-faint); font-size: 16px; }
  .rp__kpi.is-bad .rp__kpi-head i { color: var(--b2s-color-danger); }
  .rp__kpi.is-warn .rp__kpi-head i { color: var(--b2s-color-warning); }
  .rp__big { color: var(--b2s-color-heading); font-size: 26px; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .rp__kpi small { flex: 1; color: var(--b2s-color-text-muted); font-size: 12px; line-height: 1.45; }
  .rp__share { display: grid; gap: 5px; color: var(--b2s-color-text-soft); font-size: 12px; font-weight: 600; }
  .rp__bar { height: 5px; overflow: hidden; border-radius: 999px; background: var(--b2s-color-surface-muted); }
  .rp__bar i { display: block; height: 100%; border-radius: 999px; background: var(--b2s-accent-vivid); transition: width var(--b2s-motion-slow) var(--b2s-ease-out); }
  .rp__kpi.is-bad .rp__bar i { background: var(--b2s-color-danger); }
  .rp__kpi.is-warn .rp__bar i { background: var(--b2s-color-warning); }
</style>
