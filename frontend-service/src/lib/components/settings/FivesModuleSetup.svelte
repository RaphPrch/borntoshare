<script lang="ts">
  import { onMount } from 'svelte';
  import { apiGetData, apiPutData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';

  /**
   * The module « 5S et hygiène des données » on this installation: is it installed (its containers answer, its
   * databases are reachable), how to install it, and the settings of its scanner once it is on.
   */
  export let enabled = false;

  type Health = { status: string; schema: boolean };
  type Settings = { schedule_enabled: boolean; window_start: string; window_end: string; per_server: number; interval_days: number;
    full_every_days: number; hash_files_max: number; in_window?: boolean };
  let health: Health | null = null;
  let reachable: boolean | null = null;
  let form: Settings | null = null;
  let busy = false;
  let settingsFailed = false;

  onMount(load);
  $: if (enabled && reachable && !form && !settingsFailed) loadSettings();
  async function load() {
    // /health answers without the « data » envelope; no answer (503) = the module does not run here
    try {
      const response = await fetch('/api/modules/fives/health');
      health = response.ok ? ((await response.json()) as Health) : null;
      reachable = response.ok;
    } catch {
      reachable = false;
    }
  }
  async function loadSettings() {
    // A failed read shows a retry instead of « Loading… » for ever
    settingsFailed = false;
    form = await apiGetData<Settings>(fetch, '/modules/fives/settings').catch(() => null);
    settingsFailed = !form;
  }
  async function save() {
    if (!form || busy) return;
    busy = true;
    try {
      const { in_window: _ignored, ...values } = form;
      form = { ...(await apiPutData<Settings>(fetch, '/modules/fives/settings', values)) };
      toast.success(t('Scanner settings saved.'));
    } catch (error: unknown) {
      reportUiError(error, 'Unable to save the settings.', 'fives.settings');
    } finally {
      busy = false;
    }
  }
</script>

<section class="fm" aria-label={t('Module 5S on this installation')}>
  <header><h2>{t('Module 5S on this installation')}</h2>
    {#if reachable === true}<span class="fm__pill" class:is-ok={health?.schema}>{health?.schema ? t('Installed') : t('Databases unreachable')}</span>
    {:else if reachable === false}<span class="fm__pill is-warn">{t('Not installed')}</span>{/if}
  </header>

  {#if reachable === null}
    <p class="fm__muted">{t('Checking…')}</p>
  {:else if reachable === false}
    <p>{t('The license opens the module, but its containers (fives-service, fives-scanner) do not run yet: its databases are not installed on this server.')}</p>
    <p class="fm__muted">{t('Run the installation wizard again (make wizard on the server) and paste the license key at its step « Licence et modules »: it creates the two databases of the module and its own account, then deploys by itself. Nothing is deleted. Come back here afterwards.')}</p>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={load}>{t('Check again')}</button>
  {:else if !health?.schema}
    <p>{t('The module answers but cannot reach its databases: check FIVES_DB_* in .env and the account b2s_fives.')}</p>
  {:else if !enabled}
    <p class="fm__muted">{t('Switch the module on above to set its scanner.')}</p>
  {:else if form}
    <form class="fm__form" on:submit|preventDefault={save}>
      <label class="fm__check"><input type="checkbox" bind:checked={form.schedule_enabled} /> {t('Scan every folder on schedule')}</label>
      <label>{t('Window from')}<input class="b2s-input" type="time" bind:value={form.window_start} /></label>
      <label>{t('to')}<input class="b2s-input" type="time" bind:value={form.window_end} /></label>
      <label>{t('Every (days)')}<input class="b2s-input" type="number" min="1" max="90" bind:value={form.interval_days} /></label>
      <label>{t('Scans at a time per server')}<input class="b2s-input" type="number" min="1" max="8" bind:value={form.per_server} /></label>
      <label>{t('Full walk every (days)')}<input class="b2s-input" type="number" min="1" max="365" bind:value={form.full_every_days} /></label>
      <label>{t('Fingerprints per piece (duplicates)')}<input class="b2s-input" type="number" min="0" max="500000" step="1000" bind:value={form.hash_files_max} /></label>
      <p class="fm__muted fm__wide">{t('No agent on the file servers: the scanner walks them over WinRM (Kerberos) with the account of each server, at a low priority, inside the window; between two full walks only what the NTFS change journal shows as changed.')}</p>
      <div class="fm__btns"><a class="b2s-link-btn" href="/five-s/scanner">{t('Open the scanner')}</a>
        <button type="submit" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy}>{t('Save')}</button></div>
    </form>
  {:else if settingsFailed}
    <p>{t('Unable to read the scanner settings.')}</p>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={loadSettings}>{t('Check again')}</button>
  {:else}
    <p class="fm__muted">{t('Loading…')}</p>
  {/if}
</section>

<style>
  .fm { display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .fm header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .fm h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .fm p { margin: 0; font-size: var(--b2s-fs-sm); }
  .fm__muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs) !important; }
  .fm__pill { padding: 1px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); font-weight: 600; }
  .fm__pill.is-ok { background: var(--b2s-color-success-soft, #eaf7ee); color: var(--b2s-color-success-strong, #1a7f37); }
  .fm__pill.is-warn { background: var(--b2s-color-warning-soft, #fff4e5); color: var(--b2s-color-warning-strong, #9a5b00); }
  .fm button { align-self: flex-start; }
  .fm__form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .fm__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .fm__form label.fm__check { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 8px; }
  .fm__wide { grid-column: 1 / -1; }
  .fm__btns { grid-column: 1 / -1; display: flex; justify-content: flex-end; align-items: center; gap: 12px; }
</style>
