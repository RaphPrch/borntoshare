<script lang="ts">
  import { flip } from 'svelte/animate';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { onMount } from 'svelte';
  import { decideQuotaRequest, listQuotaRequests, type QuotaRequest } from '$lib/api/quotas';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatBytes } from '$lib/utils/format';

  
  interface Props {
    /**
   * Requests for more room in folders, waiting for an administrator (guardians see those of their folders).
   * Approving sends the new quota to the server at once; a refusal is explained in the folder, where its note is asked.
   */
    isAdmin?: boolean;
  }

  let { isAdmin = false }: Props = $props();

  let rows: QuotaRequest[] = $state([]);
  let busyId: number | null = $state(null);

  onMount(load);
  async function load() {
    rows = await listQuotaRequests(fetch, 'pending').catch(() => []);
  }
  async function approve(row: QuotaRequest) {
    busyId = row.id;
    try {
      await decideQuotaRequest(fetch, row.id, { decision: 'approve' });
      toast.success(t('Request approved: the new quota goes to the server.'));
      await load();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to change the quota.', 'quota.approve');
    } finally {
      busyId = null;
    }
  }
</script>

{#if rows.length}
  <section class="qr" aria-label={t('Requests for more room')}>
    <header><i class="bi bi-speedometer2" aria-hidden="true"></i><h2>{t('Requests for more room')}</h2><b>{rows.length}</b></header>
    {#each rows as row (row.id)}
      <div class="qr__row" animate:flip={{ duration: dur(MOTION.base) }} in:pop={{ y: 4 }} out:pop={{ duration: MOTION.fast, y: 0 }}>
        <span class="qr__what">
          <b>{row.folder_name || row.root_path}</b>
          <small>{row.requested_by || t('Someone')} · <RelativeTime value={row.created_at} /> · « {row.reason} »</small>
        </span>
        <span class="qr__size">{formatBytes(row.current_limit_bytes)} <i class="bi bi-arrow-right" aria-hidden="true"></i> <b>{formatBytes(row.requested_limit_bytes)}</b></span>
        <span class="qr__btns">
          <a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/storage-roots?selected=${row.storage_root_id}`}>{t('Open the folder')}</a>
          {#if isAdmin}
            <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busyId !== null} onclick={() => approve(row)}>{t('Approve')}</button>
          {/if}
        </span>
      </div>
    {/each}
  </section>
{/if}

<style>
  .qr { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .qr header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .qr h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .qr header b { padding: 0 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-warning-soft, #fff4e5); color: var(--b2s-color-warning-strong, #9a5b00); font-size: var(--b2s-fs-xs); }
  .qr__row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 16px; padding: 10px 0; border-top: 1px solid var(--b2s-color-border); }
  .qr__what { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .qr__what small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .qr__size { font-size: var(--b2s-fs-sm); font-variant-numeric: tabular-nums; white-space: nowrap; }
  .qr__btns { display: flex; gap: 8px; }
</style>
