<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';

  interface Props {
    /**
     * The module « 5S et hygiène des données » on this installation: is it installed (its containers answer, its
     * databases are reachable), and how to install it. Its scanner (schedule, frequency) is set in 5S › Scanner.
     */
    enabled?: boolean;
  }

  let { enabled = false }: Props = $props();

  type Health = { status: string; schema: boolean };
  let health: Health | null = $state(null);
  let reachable: boolean | null = $state(null);

  onMount(load);
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
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={load}>{t('Check again')}</button>
  {:else if !health?.schema}
    <p>{t('The module answers but cannot reach its databases: check FIVES_DB_* in .env and the account b2s_fives.')}</p>
  {:else if !enabled}
    <p class="fm__muted">{t('Switch the module on above to set its scanner.')}</p>
  {:else}
    <p class="fm__muted">{t('No agent on the file servers: the scanner walks them over WinRM (Kerberos) with the account of each server, at a low priority; between two full walks only what the NTFS change journal shows as changed.')}</p>
    <div class="fm__btns"><a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href="/five-s/scanner">{t('Set the schedule of the scanner')}</a></div>
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
  .fm__btns { grid-column: 1 / -1; display: flex; justify-content: flex-end; align-items: center; gap: 12px; }
</style>
