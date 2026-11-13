<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { onDestroy } from 'svelte';

  /** The identical files of a folder, group by group: which copy to keep (recorded; nothing is deleted from here). */
  type Copy = { path: string; modified: string | null };
  type Decision = { keep_path: string | null; note: string | null; decided_by: string | null; decided_at: string };
  type Group = { fingerprint: string; size: number; wasted: number; files?: number; copies: Copy[]; decision: Decision | null };

  let rootName = '';
  let groups: Group[] = [];
  let loading = true;
  let error: string | null = null;
  let filter: 'todo' | 'done' | 'all' = 'todo';
  let query = '';
  let shown = 30;
  let saving: string | null = null;

  $: rootId = Number($page.params.id);
  // ?path=…: only the duplicates with a copy in this sub-folder (opened from the explorer)
  $: folderPath = $page.url.searchParams.get('path') || '';

  // Quarantine: the copies « to delete » moved to \\share\\_B2S_Quarantaine\\<date>\\… (by the scanner), and back
  type Move = { id: number; kind?: string; path: string; quarantine_path: string; keep_path: string | null; size_bytes: number; status: string;
    error: string | null; requested_by: string | null; requested_at: string; done_at: string | null; restored_by: string | null };
  let moves: Move[] = [];
  let confirming = false;
  // Above 50 GB the move asks a second, explicit confirmation (the server refuses it otherwise)
  const LARGE = 50 * 1024 ** 3;
  let confirmLarge = false;
  $: if (!confirming) confirmLarge = false;
  let applying = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  async function loadMoves() {
    moves = (await apiGetData<{ moves: Move[] }>(fetch, `/modules/fives/storage-roots/${rootId}/quarantine`).catch(() => null))?.moves ?? moves;
    const busy = moves.some((move) => move.status === 'pending' || move.status === 'restore_pending');
    if (busy && !timer) timer = setInterval(loadMoves, 4000);
    if (!busy && timer) { clearInterval(timer); timer = null; }
  }
  onDestroy(() => timer && clearInterval(timer));
  $: inQuarantine = new Set(moves.filter((move) => ['pending', 'moved', 'restore_pending'].includes(move.status)).map((move) => move.path));
  $: toMove = decided.flatMap((group) => group.copies.filter((copy) => copy.path !== group.decision?.keep_path && !inQuarantine.has(copy.path)).map(() => group.size));
  $: toMoveBytes = toMove.reduce((sum, size) => sum + size, 0);
  async function applyDecisions() {
    if (toMoveBytes > LARGE && !confirmLarge) {
      toast.error(t('Tick the confirmation: more than 50 GB would be moved.'));
      return;
    }
    confirming = false;
    applying = true;
    try {
      const result = await apiPostData<{ queued: number; bytes: number }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups/apply`, { confirm_large: confirmLarge });
      toast.success(t('{count} copy(ies) sent to quarantine ({size}).', { count: result?.queued ?? 0, size: formatBytes(result?.bytes ?? 0) }));
      await loadMoves();
    } catch (e: unknown) {
      reportUiError(e, t('Unable to apply the decisions.'), 'fives.duplicates.apply');
    } finally {
      applying = false;
    }
  }
  async function restore(move: Move) {
    try {
      await apiPostData(fetch, `/modules/fives/storage-roots/${rootId}/quarantine/${move.id}/restore`, {});
      toast.success(t('« {name} » goes back to its place.', { name: base(move.path) }));
      await loadMoves();
    } catch (e: unknown) {
      reportUiError(e, t('Unable to restore the copy.'), 'fives.quarantine.restore');
    }
  }
  const MOVE_LABEL = (): Record<string, string> => ({ pending: t('Being moved…'), moved: t('In quarantine'), failed: t('Not moved'),
    restore_pending: t('Being restored…'), restored: t('Restored'), restore_failed: t('Not restored'), purged: t('Deleted (purge)') });

  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      groups = (await apiGetData<{ groups: Group[] }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups`, folderPath ? { path: folderPath } : undefined))?.groups ?? [];
      await loadMoves();
    } catch {
      error = t('Unable to load the duplicates of this folder.');
    } finally {
      loading = false;
    }
  });

  const base = (path: string) => path.split('\\').pop() ?? path;
  const folderOf = (path: string) => path.split('\\').slice(0, -1).join('\\') || '\\';

  async function decide(group: Group, keep: string | null) {
    saving = group.fingerprint;
    try {
      await apiPostData(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups/decision`, { fingerprint: group.fingerprint, size: group.size, keep_path: keep });
      group.decision = keep ? { keep_path: keep, note: null, decided_by: t('you'), decided_at: new Date().toISOString() } : null;
      groups = groups;
      if (keep) toast.success(t('« {name} » kept: the other copies are to delete.', { name: base(keep) }));
    } catch (e: unknown) {
      reportUiError(e, t('Unable to record the decision.'), 'fives.duplicates.decide');
    } finally {
      saving = null;
    }
  }

  $: total = groups.reduce((sum, group) => sum + group.wasted, 0);
  $: decided = groups.filter((group) => group.decision?.keep_path);
  $: freed = decided.reduce((sum, group) => sum + group.wasted, 0);
  $: visible = groups
    .filter((group) => filter === 'all' || (filter === 'done') === Boolean(group.decision?.keep_path))
    .filter((group) => !query.trim() || group.copies.some((copy) => copy.path.toLowerCase().includes(query.trim().toLowerCase())));
  $: query, filter, (shown = 30);

  const exportDecisions = () =>
    downloadCsv(csvFilename(`doublons-decisions-${rootName}`), [
      { header: t('Fingerprint'), value: (row: any) => row.fingerprint },
      { header: t('Size'), value: (row: any) => row.size },
      { header: t('Keep'), value: (row: any) => row.keep },
      { header: t('To delete'), value: (row: any) => row.drop },
      { header: t('Decided by'), value: (row: any) => row.by }
    ], decided.map((group) => ({
      fingerprint: group.fingerprint, size: group.size, keep: group.decision?.keep_path,
      drop: group.copies.filter((copy) => copy.path !== group.decision?.keep_path).map((copy) => copy.path).join(' | '), by: group.decision?.decided_by ?? ''
    })));
</script>

<div class="dd">
  <div class="dd__top">
    <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/explore/${rootId}`}><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('Explorer')}</a>
    <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/report/${rootId}`}><i class="bi bi-file-earmark-text" aria-hidden="true"></i>{t('Report')}</a>
  </div>
  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else}
    <header class="dd__head">
      <h1>{t('Duplicates · {name}', { name: rootName })}</h1>
      <p>{t('Identical files (same fingerprint: same size and same content). Choose the copy to keep; the decision is recorded, nothing is deleted from here.')}</p>
      {#if folderPath}<p class="dd__scope"><i class="bi bi-funnel" aria-hidden="true"></i>{t('Duplicates of « {path} »', { path: folderPath })} · <a href={`/five-s/duplicates/${rootId}`}>{t('see all')}</a></p>{/if}
    </header>
    <section class="dd__kpis">
      <div><span>{t('Groups')}</span><b>{groups.length.toLocaleString('fr-FR')}</b></div>
      <div><span>{t('Space lost')}</span><b>{formatBytes(total)}</b></div>
      <div><span>{t('Decided')}</span><b>{decided.length.toLocaleString('fr-FR')} / {groups.length.toLocaleString('fr-FR')}</b></div>
      <div class="is-ok"><span>{t('To free once applied')}</span><b>{formatBytes(freed)}</b></div>
    </section>
    <div class="dd__tools">
      <div class="dd__seg" role="radiogroup" aria-label={t('Show')}>
        <button type="button" class:is-on={filter === 'todo'} on:click={() => (filter = 'todo')}>{t('To decide')}</button>
        <button type="button" class:is-on={filter === 'done'} on:click={() => (filter = 'done')}>{t('Decided')}</button>
        <button type="button" class:is-on={filter === 'all'} on:click={() => (filter = 'all')}>{t('All')}</button>
      </div>
      <input class="b2s-input" placeholder={t('Filter by name or path…')} bind:value={query} aria-label={t('Filter by name or path')} />
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!decided.length} on:click={exportDecisions}><i class="bi bi-download" aria-hidden="true"></i>{t('Export the decisions')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary dd__apply" disabled={!toMove.length || applying} on:click={() => (confirming = true)}>
        <i class="bi bi-archive" aria-hidden="true"></i>{t('Move the {count} copies to quarantine', { count: toMove.length })}
      </button>
    </div>

    {#each visible.slice(0, shown) as group (group.fingerprint + group.size)}
      <article class="dd__group" class:is-done={Boolean(group.decision?.keep_path)}>
        <header>
          <div>
            <b>{base(group.copies[0]?.path ?? '')}</b>
            <small>{formatBytes(group.size)} × {Math.max(group.files ?? 0, group.copies.length)} · {t('{size} lost', { size: formatBytes(group.wasted) })}</small>
          </div>
          <code class="dd__fp" title={group.fingerprint}>{t('Fingerprint')} {group.fingerprint.slice(0, 16)}…</code>
        </header>
        <ul>
          {#each group.copies as copy (copy.path)}
            {@const kept = group.decision?.keep_path === copy.path}
            <li class:is-kept={kept} class:is-drop={Boolean(group.decision?.keep_path) && !kept}>
              <i class={`bi ${kept ? 'bi-check-circle-fill' : group.decision?.keep_path ? 'bi-trash3' : 'bi-file-earmark'}`} aria-hidden="true"></i>
              <div class="dd__copy">
                <span class="dd__name">{base(copy.path)}</span>
                <code title={copy.path} data-copy={copy.path}>{folderOf(copy.path)}</code>
              </div>
              <span class="dd__date">{copy.modified ? formatDateTime(copy.modified) : '—'}</span>
              {#if kept}
                <span class="dd__badge is-keep">{t('Kept')}</span>
              {:else if group.decision?.keep_path}
                <span class="dd__badge is-drop">{t('To delete')}</span>
              {:else}
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={saving === group.fingerprint} on:click={() => decide(group, copy.path)}>{t('Keep this one')}</button>
              {/if}
            </li>
          {/each}
          {#if (group.files ?? 0) > group.copies.length}<li class="dd__more">{t('and {count} more copies not listed (the walk keeps 5 paths per group)', { count: (group.files ?? 0) - group.copies.length })}</li>{/if}
        </ul>
        {#if group.decision?.keep_path}
          <footer>{t('Decided by {who}, {when}', { who: group.decision.decided_by ?? '—', when: formatDateTime(group.decision.decided_at) })}
            · <button type="button" class="b2s-link-btn" disabled={saving === group.fingerprint} on:click={() => decide(group, null)}>{t('Change my mind')}</button></footer>
        {/if}
      </article>
    {:else}
      <p class="dd__empty">{filter === 'todo' && groups.length ? t('Every group is decided.') : t('No duplicate known in this folder.')}</p>
    {/each}
    {#if visible.length > shown}<button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => (shown += 50)}>{t('Show more ({count} groups)', { count: visible.length })}</button>{/if}
    <p class="dd__hint">{t('The groups come from the inventory of the biggest files (1 MB and more).')}</p>

    {#if moves.length}
      <section class="dd__q">
        <header><h2><i class="bi bi-archive" aria-hidden="true"></i>{t('Quarantine')}</h2>
          <small>{t('The copies moved stay in « _B2S_Quarantaine » at the root of the share, with their path: restore them within 30 days, then they are deleted for good.')}</small></header>
        <table class="b2s-table">
          <thead><tr><th>{t('Copy')}</th><th class="dd__num">{t('Size')}</th><th>{t('State')}</th><th>{t('By')}</th><th></th></tr></thead>
          <tbody>
            {#each moves as move (move.id)}
              <tr>
                <td class="dd__mpath"><span>{base(move.path)}</span><code title={move.path} data-copy={move.path}>{folderOf(move.path)}</code>{#if move.error}<small class="dd__err">{move.error}</small>{/if}</td>
                <td class="dd__num">{formatBytes(move.size_bytes)}</td>
                <td><span class={`dd__state is-${move.status}`}>{move.kind === 'archive' && move.status === 'moved' ? t('Archived') : MOVE_LABEL()[move.status] ?? move.status}</span></td>
                <td class="dd__by">{move.restored_by && move.status.startsWith('restor') ? move.restored_by : move.requested_by ?? '—'}<small>{formatDateTime(move.done_at ?? move.requested_at)}</small></td>
                <td>{#if move.status === 'moved' || move.status === 'restore_failed'}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={() => restore(move)}>{t('Restore')}</button>{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
  {/if}
</div>

<ConfirmActionModal
  open={confirming}
  title={t('Move the copies to quarantine')}
  subtitle={t('{count} copies ({size}) leave their folder for « _B2S_Quarantaine » on the same share. The copy kept is checked first, a copy changed since the scan is left as it is, and each one can be restored.', { count: toMove.length, size: formatBytes(toMoveBytes) })}
  confirmLabel={t('Move to quarantine')}
  onConfirm={applyDecisions}
  onClose={() => (confirming = false)}
>
  {#if toMoveBytes > LARGE}
    <label class="dd__large"><input type="checkbox" bind:checked={confirmLarge} />{t('I confirm moving {size}: a large volume', { size: formatBytes(toMoveBytes) })}</label>
  {/if}
</ConfirmActionModal>

<style>
  .dd { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; min-width: 0; padding: var(--b2s-page-padding); }
  .dd__top { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .dd__top a { display: inline-flex; gap: 6px; align-items: center; }
  .dd__head h1 { margin: 0 0 4px; font-size: 24px; }
  .dd__head p { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .dd__kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .dd__kpis > div { display: grid; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: 10px; background: var(--b2s-color-surface, #fff); }
  .dd__kpis span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__kpis b { font-size: 20px; }
  .dd__kpis .is-ok b { color: var(--b2s-color-success-strong, #1a7f37); }
  .dd__tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .dd__tools .b2s-input { width: 280px; }
  .dd__seg { display: inline-flex; padding: 2px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); }
  .dd__seg button { padding: 4px 12px; border: 0; border-radius: 999px; background: none; cursor: pointer; font-size: var(--b2s-fs-sm); }
  .dd__seg button.is-on { background: var(--b2s-topbar-bg, #0e1218); color: #fff; }
  .dd__group { border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); overflow: hidden; }
  .dd__group.is-done { border-color: #a6d8b4; }
  .dd__group > header { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 10px 14px; background: var(--b2s-color-surface-muted, #f6f7f9); }
  .dd__group > header b { display: block; font-size: 15px; }
  .dd__group > header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__fp { font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); white-space: nowrap; }
  .dd__group ul { margin: 0; padding: 0; list-style: none; }
  .dd__group li { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto auto; gap: 12px; align-items: center; padding: 8px 14px; border-top: 1px solid var(--b2s-color-border-soft, #eef1f5); }
  .dd__group li.is-kept { background: #effaf2; }
  .dd__group li.is-kept i { color: #1a7f37; }
  .dd__group li.is-drop { opacity: 0.65; }
  .dd__group li.is-drop i { color: #b42318; }
  .dd__copy { display: grid; min-width: 0; }
  .dd__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .dd__copy code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .dd__date { white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .dd__badge { padding: 2px 10px; border-radius: 999px; font-size: var(--b2s-fs-xs); font-weight: 600; }
  .dd__badge.is-keep { background: #d1f0da; color: #1a7f37; }
  .dd__badge.is-drop { background: #fde2e1; color: #b42318; }
  .dd__group footer { padding: 8px 14px; border-top: 1px solid var(--b2s-color-border-soft, #eef1f5); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__empty { padding: 24px; color: var(--b2s-color-text-muted); text-align: center; }
  .dd__apply { margin-left: auto; }
  .dd__q { padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .dd__q header { display: grid; gap: 2px; margin-bottom: 10px; }
  .dd__q h2 { display: flex; gap: 8px; align-items: center; margin: 0; font-size: 16px; }
  .dd__q header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__mpath { display: grid; max-width: 560px; }
  .dd__mpath code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .dd__err { color: #b42318; font-size: var(--b2s-fs-xs); }
  .dd__num { text-align: right; white-space: nowrap; }
  .dd__by { display: grid; font-size: var(--b2s-fs-sm); }
  .dd__by small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__state { padding: 2px 10px; border-radius: 999px; font-size: var(--b2s-fs-xs); font-weight: 600; background: #eef1f5; }
  .dd__state.is-moved { background: #fff4e5; color: #b45309; }
  .dd__state.is-restored { background: #d1f0da; color: #1a7f37; }
  .dd__state.is-failed, .dd__state.is-restore_failed { background: #fde2e1; color: #b42318; }
  .dd__scope { display: inline-flex; gap: 6px; align-items: center; margin-top: 6px !important; padding: 4px 12px; border-radius: 999px; background: #EEF2FF; color: #3730A3 !important; font-size: var(--b2s-fs-sm); }
  .dd__more { display: block !important; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__large { display: flex; gap: 8px; align-items: center; margin-top: 10px; font-weight: 600; color: #9A3412; }
  .dd__hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
