<script lang="ts">

  import { onMount, untrack } from 'svelte';
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
  import FolderHeader from '../../FolderHeader.svelte';
  import { readParam, writeParams } from '$lib/utils/url-state';

  /** The identical files of a folder, group by group: which copy to keep (recorded; nothing is deleted from here). */
  type Copy = { path: string; modified: string | null };
  type Decision = { keep_path: string | null; note: string | null; decided_by: string | null; decided_at: string };
  type Group = { fingerprint: string; size: number; wasted: number; files?: number; copies: Copy[]; decision: Decision | null };

  let rootName = $state('');
  let rootPath = $state('');
  let groups = $state<Group[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let filter = $state<'todo' | 'done' | 'all'>(readParam('filter', 'todo', ['todo', 'done', 'all'] as const));
  $effect(() => writeParams({ filter: filter === 'todo' ? null : filter }));
  let query = $state('');
  let shown = $state(30);
  let saving = $state<string | null>(null);


  // Quarantine: the copies « to delete » moved to \\share\\_B2S_Quarantaine\\<date>\\… (by the scanner), and back
  type Move = { id: number; kind?: string; path: string; quarantine_path: string; keep_path: string | null; size_bytes: number; status: string;
    error: string | null; requested_by: string | null; requested_at: string; done_at: string | null; restored_by: string | null; content_sha256?: string | null };
  let moves = $state<Move[]>([]);
  let confirming = $state(false);
  // Above 50 GB the move asks a second, explicit confirmation (the server refuses it otherwise)
  const LARGE = 50 * 1024 ** 3;
  let confirmLarge = $state(false);
  let applying = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;
  async function loadMoves() {
    moves = (await apiGetData<{ moves: Move[] }>(fetch, `/modules/fives/storage-roots/${rootId}/quarantine`).catch(() => null))?.moves ?? moves;
    const busy = moves.some((move) => move.status === 'pending' || move.status === 'restore_pending');
    if (busy && !timer) timer = setInterval(loadMoves, 4000);
    if (!busy && timer) { clearInterval(timer); timer = null; }
  }
  onDestroy(() => timer && clearInterval(timer));
  async function applyDecisions() {
    if (toMoveBytes > LARGE && !confirmLarge) {
      toast.error(t('Tick the confirmation: more than 50 GB would be moved.'));
      return;
    }
    confirming = false;
    applying = true;
    try {
      const result = await apiPostData<{ queued: number; bytes: number; skipped?: number }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups/apply`, { confirm_large: confirmLarge });
      toast.success(t('{count} copy(ies) to verify then move ({size}): the scanner compares each one with the copy kept first.', { count: result?.queued ?? 0, size: formatBytes(result?.bytes ?? 0) }));
      if (result?.skipped) toast.info(t('{count} copy(ies) left aside: the copy kept is no longer known or the path is outside the folder. Measure the folder again.', { count: result.skipped }));
      await loadMoves();
    } catch (e: unknown) {
      reportUiError(e, t('Unable to apply the decisions.'), 'fives.duplicates.apply');
    } finally {
      applying = false;
    }
  }
  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      rootPath = String(overview?.root_path ?? '');
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

  async function decide(group: Group, keep: string | null, undoable = true) {
    const before = group.decision?.keep_path ?? null;
    saving = group.fingerprint;
    try {
      await apiPostData(fetch, `/modules/fives/storage-roots/${rootId}/duplicate-groups/decision`, { fingerprint: group.fingerprint, size: group.size, keep_path: keep });
      group.decision = keep ? { keep_path: keep, note: null, decided_by: t('you'), decided_at: new Date().toISOString() } : null;
      groups = groups;
      if (keep && undoable) toast.success(t('« {name} » kept: the other copies are to delete.', { name: base(keep) }),
        { action: { label: t('Undo'), run: () => decide(group, before, false) } });
    } catch (e: unknown) {
      reportUiError(e, t('Unable to record the decision.'), 'fives.duplicates.decide');
    } finally {
      saving = null;
    }
  }


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
  let rootId = $derived(Number($page.params.id));
  // ?path=…: only the duplicates with a copy in this sub-folder (opened from the explorer)
  let folderPath = $derived($page.url.searchParams.get('path') || '');
  $effect.pre(() => {
    if (!confirming) confirmLarge = false;
  });
  let inQuarantine = $derived(new Set(moves.filter((move) => ['pending', 'moved', 'restore_pending'].includes(move.status)).map((move) => move.path)));
  let decided = $derived(groups.filter((group) => group.decision?.keep_path));
  let toMove = $derived(decided.flatMap((group) => group.copies.filter((copy) => copy.path !== group.decision?.keep_path && !inQuarantine.has(copy.path)).map(() => group.size)));
  let toMoveBytes = $derived(toMove.reduce((sum, size) => sum + size, 0));
  let total = $derived(groups.reduce((sum, group) => sum + group.wasted, 0));
  let freed = $derived(decided.reduce((sum, group) => sum + group.wasted, 0));
  let visible = $derived(groups
    .filter((group) => filter === 'all' || (filter === 'done') === Boolean(group.decision?.keep_path))
    .filter((group) => !query.trim() || group.copies.some((copy) => copy.path.toLowerCase().includes(query.trim().toLowerCase()))));
  $effect.pre(() => {
    void [query, filter]; // only these start it again (as the former « $: »)
    untrack(() => { shown = 30; });
  });
</script>

<div class="dd">
  <FolderHeader {rootId} name={rootName} path={rootPath} current="duplicates" counts={{ duplicates: groups.length - decided.length }} />
  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else}
    <header class="dd__head">
      <p>{t('Probable duplicates: same size and same fingerprint (start and end of the files). Choose the copy to keep; the decision is recorded, nothing moves from here.')}</p>
      <p class="dd__safe"><i class="bi bi-shield-check" aria-hidden="true"></i>{t('Before a copy moves to quarantine, the scanner compares its whole content with the copy kept, on the server: a copy that differs, or that changed since the measure, stays in place.')}</p>
      {#if folderPath}<p class="dd__scope"><i class="bi bi-funnel" aria-hidden="true"></i>{t('Duplicates of « {path} »', { path: folderPath })} · <a href={`/five-s/duplicates/${rootId}`}>{t('see all')}</a></p>{/if}
    </header>
    <section class="v2-stats">
      <div class="v2-stat"><i class="bi bi-collection" aria-hidden="true"></i><small>{t('Groups')}</small><b>{groups.length.toLocaleString('fr-FR')}</b></div>
      <div class="v2-stat"><i class="bi bi-copy is-warn" aria-hidden="true"></i><small>{t('Space lost')}</small><b>{formatBytes(total)}</b></div>
      <div class="v2-stat"><i class="bi bi-check2-square" aria-hidden="true"></i><small>{t('Decided')}</small><b>{decided.length.toLocaleString('fr-FR')} / {groups.length.toLocaleString('fr-FR')}</b></div>
      <div class="v2-stat"><i class="bi bi-recycle" aria-hidden="true"></i><small>{t('To free once applied')}</small><b class="dd__ok-figure">{formatBytes(freed)}</b></div>
    </section>
    <div class="dd__tools">
      <div class="dd__seg" role="radiogroup" aria-label={t('Show')}>
        <button type="button" class:is-on={filter === 'todo'} onclick={() => (filter = 'todo')}>{t('To decide')}</button>
        <button type="button" class:is-on={filter === 'done'} onclick={() => (filter = 'done')}>{t('Decided')}</button>
        <button type="button" class:is-on={filter === 'all'} onclick={() => (filter = 'all')}>{t('All')}</button>
      </div>
      <input class="b2s-input" placeholder={t('Filter by name or path…')} bind:value={query} aria-label={t('Filter by name or path')} />
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!decided.length} onclick={exportDecisions}><i class="bi bi-download" aria-hidden="true"></i>{t('Export the decisions')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary dd__apply" disabled={!toMove.length || applying} onclick={() => (confirming = true)}>
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
                <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={saving === group.fingerprint} onclick={() => decide(group, copy.path)}>{t('Keep this one')}</button>
              {/if}
            </li>
          {/each}
          {#if (group.files ?? 0) > group.copies.length}<li class="dd__more">{t('and {count} more copies not listed (the walk keeps 5 paths per group)', { count: (group.files ?? 0) - group.copies.length })}</li>{/if}
        </ul>
        {#if group.decision?.keep_path}
          <footer>{t('Decided by {who}, {when}', { who: group.decision.decided_by ?? '—', when: formatDateTime(group.decision.decided_at) })}
            · <button type="button" class="b2s-link-btn" disabled={saving === group.fingerprint} onclick={() => decide(group, null)}>{t('Change my mind')}</button></footer>
        {/if}
      </article>
    {:else}
      <p class="dd__empty">{filter === 'todo' && groups.length ? t('Every group is decided.') : t('No duplicate known in this folder.')}</p>
    {/each}
    {#if visible.length > shown}<button type="button" class="b2s-btn b2s-btn-secondary" onclick={() => (shown += 50)}>{t('Show more ({count} groups)', { count: visible.length })}</button>{/if}
    <p class="dd__hint">{t('The groups come from the inventory of the biggest files (1 MB and more).')}</p>

    {#if moves.length}
      <p class="dd__qlink"><i class="bi bi-archive" aria-hidden="true"></i>
        {t('{count} copy(ies) or folder(s) of this folder in quarantine or archived.', { count: moves.filter((move) => ['pending', 'moved', 'restore_pending'].includes(move.status)).length })}
        <a href={`/five-s/scanner?tab=quarantine&root=${rootId}`}>{t('See the quarantine')}</a></p>
    {/if}
  {/if}
</div>

<ConfirmActionModal
  open={confirming}
  title={t('Move the copies to quarantine')}
  subtitle={t('{count} copies ({size}) leave their folder for « _B2S_Quarantaine » on the same share. Each one is first compared in full with the copy kept: only an identical copy moves, and each one can be restored.', { count: toMove.length, size: formatBytes(toMoveBytes) })}
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
  .dd__head p { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .dd__tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .dd__tools .b2s-input { width: 280px; }
  .dd__seg { display: inline-flex; padding: 2px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); }
  .dd__seg button { padding: 4px 12px; border: 0; border-radius: 999px; background: none; cursor: pointer; font-size: var(--b2s-fs-sm); }
  .dd__seg button.is-on { background: var(--b2s-topbar-bg, var(--b2s-accent)); color: #fff; }
  .dd__group { border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); overflow: hidden; }
  .dd__group.is-done { border-color: var(--b2s-color-success-border); }
  .dd__group > header { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 10px 14px; background: var(--b2s-color-surface-muted); }
  .dd__group > header b { display: block; font-size: 15px; }
  .dd__group > header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__fp { font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); white-space: nowrap; }
  .dd__group ul { margin: 0; padding: 0; list-style: none; }
  .dd__group li { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto auto; gap: 12px; align-items: center; padding: 8px 14px; border-top: 1px solid var(--b2s-color-border-soft); }
  .dd__group li.is-kept { background: var(--b2s-color-success-soft); }
  .dd__group li.is-kept i { color: var(--b2s-color-success-strong); }
  .dd__group li.is-drop { opacity: 0.65; }
  .dd__group li.is-drop i { color: var(--b2s-color-danger-strong); }
  .dd__copy { display: grid; min-width: 0; }
  .dd__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .dd__copy code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .dd__date { white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .dd__badge { padding: 2px 10px; border-radius: 999px; font-size: var(--b2s-fs-xs); font-weight: 600; }
  .dd__badge.is-keep { background: var(--b2s-color-success-border); color: var(--b2s-color-success-strong); }
  .dd__badge.is-drop { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .dd__group footer { padding: 8px 14px; border-top: 1px solid var(--b2s-color-border-soft); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__empty { padding: 24px; color: var(--b2s-color-text-muted); text-align: center; }
  .dd__apply { margin-left: auto; }
  .dd__safe { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px !important; padding: 8px 12px; border-radius: 10px; background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong) !important; }
  .dd__scope { display: inline-flex; gap: 6px; align-items: center; margin-top: 6px !important; padding: 4px 12px; border-radius: 999px; background: var(--b2s-accent-soft); color: var(--b2s-accent-strong) !important; font-size: var(--b2s-fs-sm); }
  .dd__more { display: block !important; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__large { display: flex; gap: 8px; align-items: center; margin-top: 10px; font-weight: 600; color: var(--b2s-color-warning-strong); }
  .dd__hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .dd__ok-figure { color: var(--b2s-color-success-strong); }
  .dd__qlink { display: flex; gap: 8px; align-items: center; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
</style>
