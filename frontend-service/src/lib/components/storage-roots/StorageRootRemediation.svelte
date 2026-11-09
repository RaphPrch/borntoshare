<script lang="ts">
  import { apiGetData, apiPostData } from '$lib/api/client';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatDate } from '$lib/utils/format';
  import { pop } from '$lib/utils/motion';

  /**
   * Correction of the passwords found in the folder: an administrator asks the guardians to remove or move the
   * files before a due date. Each new scan looks again: done by itself when they are gone, overdue (critical alert)
   * when they are still there at the due date — the folder is scanned again on that day.
   */
  export let rootId: number | null = null;
  export let isAdmin = false;
  /** Files holding passwords in the last scan (without the false positives) */
  export let passwordFiles = 0;
  /** Changes after each scan: the state is read again */
  export let refreshKey: unknown = null;

  type Item = { id: number; status: 'open' | 'overdue' | 'done' | 'cancelled'; files_at_request: number; paths: string[]; note: string | null;
    requested_by: string | null; requested_at: string; due_at: string; closed_at: string | null; closed_by: string | null };
  type State = { current: Item | null; history: Item[] };
  let state: State | null = null;
  let loadedFor = '';
  let asking = false;
  let busy = false;
  let days = 14;
  let note = '';

  $: key = `${rootId}:${String(refreshKey)}`;
  $: if (rootId && key !== loadedFor) load();
  async function load() {
    loadedFor = key;
    asking = false;
    state = await apiGetData<State>(fetch, `/storage-roots/${rootId}/remediation`).catch(() => null);
  }
  $: current = state?.current ?? null;
  // The last one closed by the scan, shown for a month: « corrected on … »
  $: lastDone = (state?.history ?? []).find((item) => item.status === 'done' && item.closed_at && Date.now() - Date.parse(item.closed_at) < 30 * 86400000) ?? null;
  $: daysLeft = current ? Math.ceil((Date.parse(current.due_at) - Date.now()) / 86400000) : 0;

  async function ask() {
    if (busy || !rootId) return;
    busy = true;
    try {
      state = await apiPostData<State>(fetch, `/storage-roots/${rootId}/remediation`, { due_days: days, note: note.trim() || null });
      asking = false;
      note = '';
      toast.success(t('Correction asked to the guardians.'));
    } catch (error: unknown) {
      reportUiError(error, 'Unable to ask for the correction.', 'remediation.ask');
    } finally {
      busy = false;
    }
  }
  async function cancel() {
    if (busy || !rootId) return;
    busy = true;
    try {
      state = await apiPostData<State>(fetch, `/storage-roots/${rootId}/remediation/cancel`, {});
      toast.success(t('Correction cancelled.'));
    } catch (error: unknown) {
      reportUiError(error, 'Unable to cancel the correction.', 'remediation.cancel');
    } finally {
      busy = false;
    }
  }
</script>

{#if current}
  <div class="rm" class:is-late={current.status === 'overdue'} in:pop={{ y: 4 }}>
    <i class={`bi ${current.status === 'overdue' ? 'bi-alarm' : 'bi-hourglass-split'}`} aria-hidden="true"></i>
    <div>
      <b>{current.status === 'overdue'
        ? t('Correction overdue since {date}: the passwords are still there', { date: formatDate(current.due_at) })
        : daysLeft > 0 ? t('Correction asked: {days} day(s) left (until {date})', { days: daysLeft, date: formatDate(current.due_at) })
        : t('Due date reached: the folder is scanned again')}</b>
      <small>{t('Asked by {who}', { who: current.requested_by ?? '—' })} · <RelativeTime value={current.requested_at} />
        · {t('{count} file(s) to remove or move', { count: current.files_at_request })}{current.note ? ` · « ${current.note} »` : ''}</small>
    </div>
    {#if isAdmin}<button type="button" class="b2s-link-btn" disabled={busy} on:click={cancel}>{t('Cancel')}</button>{/if}
  </div>
{:else if passwordFiles > 0 && isAdmin}
  {#if asking}
    <div class="rm__form" in:pop={{ y: 4 }}>
      <label>{t('Deadline')}
        <select class="b2s-input" bind:value={days}>{#each [7, 14, 30] as value (value)}<option {value}>{t('{days} days', { days: value })}</option>{/each}</select>
      </label>
      <label class="rm__wide">{t('Message to the guardians (optional)')}
        <input class="b2s-input" bind:value={note} maxlength="500" placeholder={t('e.g. Put the accesses in the team vault')} /></label>
      <p class="rm__wide rm__hint">{t('The guardians see it in the to-do list of the folder (and by e-mail when notifications are on). The folder is scanned again at the due date.')}</p>
      <div class="rm__btns rm__wide">
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (asking = false)}>{t('Cancel')}</button>
        <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy} on:click={ask}>{t('Ask the guardians')}</button>
      </div>
    </div>
  {:else}
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm rm__ask" on:click={() => (asking = true)}>
      <i class="bi bi-send" aria-hidden="true"></i>{t('Ask the guardians to correct it')}</button>
  {/if}
{:else if lastDone}
  <p class="rm__done"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('Corrected {when}: the scan no longer finds the passwords.', { when: formatDate(lastDone.closed_at) })}</p>
{/if}

<style>
  .rm { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); font-size: var(--b2s-fs-sm); }
  .rm > i { margin-top: 2px; color: var(--b2s-color-info-strong); }
  .rm.is-late { background: var(--b2s-color-danger-soft, #fdecea); }
  .rm.is-late > i, .rm.is-late b { color: var(--b2s-color-danger-strong, #b42318); }
  .rm div { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .rm small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rm__ask { align-self: flex-start; }
  .rm__ask i { margin-right: 6px; }
  .rm__form { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 10px; padding: 12px; border: 1px dashed var(--b2s-color-border-strong); border-radius: 12px; }
  .rm__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .rm__wide { grid-column: 1 / -1; }
  .rm__form label.rm__wide { grid-column: 2 / -1; }
  .rm__hint { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rm__btns { display: flex; justify-content: flex-end; gap: 8px; }
  .rm__done { display: flex; gap: 8px; align-items: center; margin: 0; color: var(--b2s-color-success-strong, #1a7f37); font-size: var(--b2s-fs-sm); }
</style>
