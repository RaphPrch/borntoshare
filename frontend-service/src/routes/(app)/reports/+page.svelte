<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGetData } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { fivesEnabled } from '$lib/utils/features';
  import { licenseGroups } from '$lib/utils/insights';

  /** Insights & Recommendations › Reports: the reports to print or save as PDF (the core's, then the 5S module's). */
  type Report = { key: string; title: string; description: string; source?: 'core' | 'fives'; license?: 'core' | 'governance' | 'fives' };
  const ICONS: Record<string, string> = { storage: 'bi-hdd-stack', infrastructure: 'bi-activity', alerts: 'bi-bell', security: 'bi-shield-lock',
    governance: 'bi-diagram-3', exposure: 'bi-globe2', guardians: 'bi-person-badge', requests: 'bi-inbox', 'fives-5s': 'bi-stars', 'fives-hygiene': 'bi-recycle' };
  // Grouped by what brings them: always there, the access governance, the 5S module (its own reports and the sensitivity scan)
  const GROUPS = licenseGroups();
  const groupOf = (report: Report) => report.license ?? (report.source === 'fives' ? 'fives' : 'core');
  let reports = $state<Report[] | null>(null);

  onMount(async () => {
    const [core, module] = await Promise.all([
      apiGetData<Report[]>(fetch, '/insights/reports').catch(() => []),
      $fivesEnabled ? apiGetData<Report[]>(fetch, '/modules/fives/reports').catch(() => []) : Promise.resolve([] as Report[])
    ]);
    reports = [...core, ...module];
  });
</script>

<svelte:head><title>Reports · BornToShare</title></svelte:head>

<section class="v2 rp">
  <div class="v2-head">
    <div>
      <h1>Reports</h1>
      <p>{t('Storage, security, access and 5S reports, to print or save as PDF.')}</p>
    </div>
  </div>

  {#if !reports}
    <div class="v2-sec"><LoadingState block skeleton="rows" rows={2} /></div>
  {:else}
    {#each GROUPS as group (group.key)}
      {@const items = reports.filter((report) => groupOf(report) === group.key)}
      {#if items.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{group.title}</h2><span class="v2-tag is-mut">{items.length}</span>
            <div class="v2-sh__r"><span class="v2-hint">{group.hint}</span></div></div>
          <div class="rp__reports">
            {#each items as report (report.key)}
              <a class="rp__report" href={`/reports/${report.key}`}>
                <span class="rp__icon"><i class={`bi ${ICONS[report.key] ?? 'bi-file-earmark-text'}`} aria-hidden="true"></i></span>
                <b>{report.title}</b>
                <small>{report.description}</small>
                <span class="rp__open">{t('Open the report')} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
              </a>
            {/each}
          </div>
        </div>
      {/if}
    {/each}
    <p class="v2-hint">{t('Each report can be narrowed: zone, server, tag, state of the folders or an express search, then printed or saved as PDF.')}</p>
  {/if}
</section>

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
</style>
