<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGetData } from '$lib/api/client';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { fivesEnabled } from '$lib/utils/features';

  /** The reports of the governed folders: read on screen, printed or saved as PDF from the browser. */
  type Report = { key: string; title: string; description: string; source?: 'core' | 'fives' };
  const ICONS: Record<string, string> = { storage: 'bi-hdd-stack', security: 'bi-shield-lock', governance: 'bi-diagram-3', 'fives-5s': 'bi-stars', 'fives-hygiene': 'bi-recycle' };
  let reports = $state<Report[] | null>(null);
  onMount(async () => {
    // The reports of the core, then those of the 5S module when it is on
    const [core, module] = await Promise.all([
      apiGetData<Report[]>(fetch, '/insights/reports').catch(() => []),
      $fivesEnabled ? apiGetData<Report[]>(fetch, '/modules/fives/reports').catch(() => []) : Promise.resolve([] as Report[])
    ]);
    reports = [...core, ...module];
  });
</script>

<section class="b2s-page b2s-page--admin rp">
  <header>
    <h1>{t('Reports')}</h1>
    <p>{t('Built from the last measures, scans and ACL reads of the folders you may see. Print them or save them as PDF.')}</p>
  </header>
  {#if !reports}
    <LoadingState block skeleton="rows" rows={4} />
  {:else}
    <div class="rp__grid">
      {#each reports as report (report.key)}
        <a class="rp__card" href={`/reports/${report.key}`}>
          <span class="rp__icon"><i class={`bi ${ICONS[report.key] ?? 'bi-file-earmark-text'}`} aria-hidden="true"></i></span>
          <b>{report.title}</b>
          <small>{report.description}</small>
          <span class="rp__open">{t('Open the report')} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
        </a>
      {/each}
    </div>
  {/if}
</section>

<style>
  .rp { display: flex; flex-direction: column; gap: 20px; padding: var(--b2s-page-padding, 24px 28px); }
  .rp h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 650; }
  .rp header p { margin: 4px 0 0; color: var(--b2s-color-text-muted); }
  .rp__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .rp__card { display: flex; flex-direction: column; gap: 8px; padding: 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; text-decoration: none; transition: box-shadow var(--b2s-motion-base) var(--b2s-ease-out), transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .rp__card:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(14, 18, 24, 0.08); }
  .rp__icon { display: grid; place-items: center; width: 42px; height: 42px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 20px; }
  .rp__card b { font-size: var(--b2s-fs-lg, 18px); font-weight: 650; }
  .rp__card small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .rp__open { margin-top: auto; padding-top: 6px; color: var(--b2s-color-info-strong); font-size: var(--b2s-fs-sm); font-weight: 600; }
</style>
