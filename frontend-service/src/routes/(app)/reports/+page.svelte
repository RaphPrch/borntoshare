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

  /**
   * Insights & Recommendations (v2): what the last measures, scans and ACL reads of the folders reveal, each with
   * the folders concerned one click away (the express search of Storage Roots), then the reports to print.
   */
  type Report = { key: string; title: string; description: string; source?: 'core' | 'fives' };
  type Root = Record<string, any>;
  const ICONS: Record<string, string> = { storage: 'bi-hdd-stack', security: 'bi-shield-lock', governance: 'bi-diagram-3', 'fives-5s': 'bi-stars', 'fives-hygiene': 'bi-recycle' };
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
    if (key === 'policy') void goto('/admin/policies');
    if (key === 'copy') await navigator.clipboard?.writeText(insight.query).catch(() => null);
  }
</script>

<section class="v2 rp">
  <div class="v2-head">
    <div>
      <h1>Insights &amp; Recommendations</h1>
      <p>{t('What the last measures, scans and ACL reads of the folders you may see reveal, and the reports to print or save as PDF.')}</p>
    </div>
    {#if isAdmin}<div class="v2-head__act"><a class="b2s-btn b2s-btn-primary" href="/admin/policies"><i class="bi bi-lightning-charge" aria-hidden="true"></i>{t('Smart policies')}</a></div>{/if}
  </div>

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Recommendations')}</h2>{#if insights.length}<span class="v2-tag is-mut">{insights.length}</span>{/if}
      <div class="v2-sh__r"><span class="v2-hint">{t('Click: the folders concerned · right click: actions')}</span></div></div>
    {#if !roots}
      <LoadingState block skeleton="rows" rows={4} />
    {:else}
      <ul class="v2-feed">
        {#each insights as insight (insight.key)}
          <li>
            <button type="button" class="v2-fi rp__ins" onclick={() => openFolders(insight)}
              oncontextmenu={(event) => { event.preventDefault(); menu = { insight, at: menuPositionFor(event) }; }}>
              <b class="rp__big">{insight.big}</b>
              <span class={`v2-dot is-${insight.tone}`}></span>
              <span class="v2-fi__t"><b>{insight.title}</b><small>{insight.detail}</small></span>
              <span class="v2-fi__r">{t('{count} folder(s)', { count: insight.count })} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
            </button>
          </li>
        {:else}
          <li class="v2-fi"><span class="v2-dot"></span><span class="v2-fi__t"><b>{t('Nothing to recommend')}</b><small>{t('The folders are well kept, or not measured yet.')}</small></span></li>
        {/each}
      </ul>
    {/if}
  </div>

  <div class="v2-sec">
    <div class="v2-sh"><h2>{t('Reports')}</h2></div>
    {#if !reports}
      <LoadingState block skeleton="rows" rows={4} />
    {:else}
      <ul class="v2-feed">
        {#each reports as report (report.key)}
          <li><a class="v2-fi" href={`/reports/${report.key}`}>
            <span class="rp__icon"><i class={`bi ${ICONS[report.key] ?? 'bi-file-earmark-text'}`} aria-hidden="true"></i></span>
            <span class="v2-fi__t"><b>{report.title}</b><small>{report.description}</small></span>
            <span class="v2-fi__r">{t('Open the report')} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
          </a></li>
        {/each}
      </ul>
    {/if}
  </div>
</section>

<ContextMenu open={menu != null} title={menu?.insight.title ?? ''} subtitle={menu?.insight.query ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  .rp__ins { gap: 16px; padding: 16px 4px; }
  .rp__big { min-width: 120px; font-size: 24px; font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .rp__icon { display: grid; place-items: center; width: 34px; height: 34px; flex: none; border-radius: 9px; background: #f0f2f5; color: #2b323d; font-size: 16px; }
</style>
