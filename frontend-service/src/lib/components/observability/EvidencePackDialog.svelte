<script lang="ts">
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import { listZones } from '$lib/api/zones';
  import { t } from '$lib/i18n';

  /**
   * Audit evidence pack (administrators): a ZIP of CSV files for a period and a scope, built by core-service with the
   * SHA-256 of every file (chained audit log, access requests, review decisions; who reaches a folder today).
   */
  let { open = false, onClose = () => {} }: { open?: boolean; onClose?: () => void } = $props();

  const iso = (date: Date) => date.toISOString().slice(0, 10);
  const today = iso(new Date());
  let since = $state(iso(new Date(Date.now() - 90 * 86_400_000)));
  let until = $state(today);
  let zoneId = $state(0);
  let zones = $state<Array<{ id: number; name: string }>>([]);
  $effect(() => {
    if (open && !zones.length) void listZones(fetch).then((list) => (zones = list.map((zone: any) => ({ id: Number(zone.id), name: String(zone.name ?? zone.code ?? zone.id) })))).catch(() => null);
  });
  // Same limits as core-service (400 days at most)
  let days = $derived((Date.parse(until) - Date.parse(since)) / 86_400_000);
  let error = $derived(!since || !until || days < 0 ? t('The period goes from the oldest date to the most recent.') : days > 400 ? t('400 days at most: shorten the period.') : null);
  let href = $derived(`/api/activity/evidence-pack?${new URLSearchParams({ since, until, ...(zoneId ? { zone_id: String(zoneId) } : {}) }).toString()}`);
</script>

<AppModal {open} {onClose} iconClass="bi bi-file-earmark-zip" title={t('Audit evidence pack')}
  subtitle={t('A ZIP of CSV files with the SHA-256 of each file: audit log, requests, review decisions.')}>
  <div class="ep">
    <label>{t('From')}<input class="b2s-input" type="date" bind:value={since} max={until} /></label>
    <label>{t('To (included)')}<input class="b2s-input" type="date" bind:value={until} max={today} /></label>
    <label class="ep__wide">{t('Scope')}
      <select class="b2s-input" bind:value={zoneId}>
        <option value={0}>{t('The whole platform')}</option>
        {#each zones as zone (zone.id)}<option value={zone.id}>{t('Zone {name}', { name: zone.name })}</option>{/each}
      </select>
    </label>
    <small class="ep__wide ep__hint">{t('For one folder: its sheet › … › Audit evidence pack.')}</small>
    {#if error}<small class="ep__wide ep__error">{error}</small>{/if}
  </div>
  {#snippet footer()}
    <button type="button" class="b2s-btn b2s-btn-secondary" onclick={onClose}>{t('Cancel')}</button>
    {#if error}<button type="button" class="b2s-btn b2s-btn-primary" disabled>{t('Download')}</button>
    {:else}<a class="b2s-btn b2s-btn-primary" {href} download onclick={() => setTimeout(onClose, 300)}><i class="bi bi-download" aria-hidden="true"></i>{t('Download')}</a>{/if}
  {/snippet}
</AppModal>

<style>
  .ep { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .ep label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .ep__wide { grid-column: 1 / -1; }
  .ep__hint { color: var(--b2s-color-text-muted); }
  .ep__error { color: var(--b2s-color-danger-strong); }
</style>
