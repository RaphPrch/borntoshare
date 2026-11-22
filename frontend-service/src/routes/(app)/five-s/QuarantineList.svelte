<script module lang="ts">
  import { t } from '$lib/i18n';

  /** A copy sent to quarantine, or a folder archived, and its way back. */
  export type Move = { id: number; storage_root_id?: number; folder_name?: string | null; kind?: string; path: string; quarantine_path: string;
    keep_path: string | null; size_bytes: number; status: string; error: string | null; requested_by: string | null; requested_at: string;
    done_at: string | null; restored_by: string | null; content_sha256?: string | null };

  export const MOVE_LABEL = (): Record<string, string> => ({ pending: t('Being moved…'), moved: t('In quarantine'), failed: t('Not moved'),
    restore_pending: t('Being restored…'), restored: t('Restored'), restore_failed: t('Not restored'), purged: t('Deleted (purge)') });

  /** Why a copy did not move, in plain words (the code comes first in the error of the scanner) */
  export function moveError(error: string | null): string {
    const code = String(error ?? '').split(':', 1)[0].trim();
    const texts: Record<string, string> = {
      CONTENT_DIFFERS: t('Not a duplicate: its whole content differs from the copy kept. Left in place.'),
      CHANGED: t('Modified since the measure: left in place. Measure the folder again.'),
      KEEP_MISSING: t('The copy to keep is no longer there: nothing was moved.'),
      SOURCE_MISSING: t('The file is no longer there.'),
      TARGET_EXISTS: t('Something is already at the destination: nothing is overwritten.'),
      SAME_FILE: t('The copy to move is the copy kept.'),
      OUTSIDE: t('Path outside the governed folder: refused.'),
      NOT_A_FILE: t('Not a file: refused.'),
      CHANGED_IN_QUARANTINE: t('The copy changed while in quarantine.')
    };
    return texts[code] ?? String(error ?? '');
  }
</script>

<script lang="ts">
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import { toast } from '$lib/stores/toast';
  import { copyText } from '$lib/utils/clipboard';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';

  /** The moves of the 5S module (quarantine of duplicates, archives) as a list: state, why, who, and the way back. */
  interface Props {
    moves: Move[];
    showFolder?: boolean;
    /** Restores these moves (one, or a selection) */
    onRestore?: (moves: Move[]) => void;
  }

  let { moves, showFolder = false, onRestore }: Props = $props();
  const restorable = (move: Move) => move.status === 'moved' || move.status === 'restore_failed';
  let selected = $state(new Set<number>());
  let chosen = $derived(moves.filter((move) => selected.has(move.id) && restorable(move)));
  const toggle = (id: number) => { const next = new Set(selected); if (next.has(id)) next.delete(id); else next.add(id); selected = next; };
  function restore(list: Move[]) {
    onRestore?.(list);
    selected = new Set();
  }

  // ---- right click on a move ----
  let menu = $state<{ move: Move; at: { x: number; y: number } } | null>(null);
  const menuItems = (move: Move): ContextMenuItem[] => [
    { key: 'restore', label: move.kind === 'archive' ? t('Bring the folder back') : t('Restore the copy'), icon: 'bi-arrow-counterclockwise',
      disabled: !onRestore || !restorable(move), hint: !restorable(move) ? MOVE_LABEL()[move.status] : undefined },
    { key: 'open', label: t('Open the governed folder'), icon: 'bi-folder2-open', disabled: !move.storage_root_id },
    { key: 'path', label: t('Copy the original path'), icon: 'bi-clipboard', separated: true },
    { key: 'qpath', label: t('Copy the path in quarantine'), icon: 'bi-clipboard' }
  ];
  async function pick(key: string) {
    const move = menu?.move;
    menu = null;
    if (!move) return;
    if (key === 'restore') restore([move]);
    else if (key === 'open') window.location.assign(`/five-s/explore/${move.storage_root_id}`);
    else if (await copyText(key === 'path' ? move.path : move.quarantine_path)) toast.success(t('Path copied.'));
  }
  const base = (path: string) => path.split('\\').pop() ?? path;
  const folderOf = (path: string) => path.split('\\').slice(0, -1).join('\\') || '\\';
  const TONE: Record<string, string> = { pending: 'info', moved: 'warn', failed: 'bad', restore_pending: 'info', restored: 'ok', restore_failed: 'bad', purged: 'mut' };
</script>

{#if chosen.length}
  <div class="v2-bulk">
    <b>{t('{count} selected', { count: chosen.length })}</b>
    <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={() => restore(chosen)}><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>{t('Restore')}</button>
    <button type="button" class="b2s-link-btn" onclick={() => (selected = new Set())}>{t('Clear the selection')}</button>
  </div>
{/if}
<div class="v2-list">
  <div class="v2-row is-head ql" class:has-folder={showFolder}>
    <span></span><span>{t('Copy or folder')}</span>{#if showFolder}<span>{t('Governed folder')}</span>{/if}<span>{t('Size')}</span><span>{t('State')}</span><span>{t('By')}</span><span></span>
  </div>
  {#each moves as move (move.id)}
    <div class="v2-row ql" class:has-folder={showFolder} role="row" tabindex="-1"
      oncontextmenu={(event) => { event.preventDefault(); menu = { move, at: menuPositionFor(event) }; }}>
      <span>{#if onRestore && restorable(move)}<input type="checkbox" checked={selected.has(move.id)} onchange={() => toggle(move.id)} aria-label={t('Select')} />{/if}</span>
      <span class="v2-nm">
        <span><i class={`bi ${move.kind === 'archive' ? 'bi-archive' : 'bi-files'}`} aria-hidden="true"></i> {base(move.path)}</span>
        <code class="v2-sub" title={move.path} data-copy={move.path}>{folderOf(move.path)}</code>
        {#if move.error}<small class={move.status === 'restored' ? 'ql__note' : 'ql__err'} title={move.error}>{moveError(move.error)}</small>{/if}
        {#if move.content_sha256 && move.status === 'moved'}<small class="ql__ok" title={`SHA-256 ${move.content_sha256}`}><i class="bi bi-shield-check" aria-hidden="true"></i> {t('Verified identical to the copy kept')}</small>{/if}
      </span>
      {#if showFolder}<span class="v2-sub"><a href={`/five-s/explore/${move.storage_root_id}`}>{move.folder_name ?? `#${move.storage_root_id}`}</a></span>{/if}
      <span>{move.kind === 'archive' && !move.size_bytes ? '—' : formatBytes(move.size_bytes)}</span>
      <span><span class={`v2-tag is-${TONE[move.status] ?? 'mut'}`}>{move.kind === 'archive' && move.status === 'moved' ? t('Archived') : MOVE_LABEL()[move.status] ?? move.status}</span></span>
      <span class="v2-nm"><span>{move.restored_by && move.status.startsWith('restor') ? move.restored_by : move.requested_by ?? '—'}</span><small class="v2-sub">{formatDateTime(move.done_at ?? move.requested_at)}</small></span>
      <span>{#if onRestore && (move.status === 'moved' || move.status === 'restore_failed')}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={() => restore([move])}>{t('Restore')}</button>{/if}</span>
    </div>
  {:else}
    <p class="v2-empty">{t('Nothing in quarantine or in the archives.')}</p>
  {/each}
</div>

<ContextMenu open={Boolean(menu)} title={menu ? (menu.move.path.split('\\').pop() ?? '') : ''} items={menu ? menuItems(menu.move) : []}
  at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={(key) => void pick(key)} />

<style>
  .ql { grid-template-columns: 24px minmax(240px, 2fr) 110px 150px 170px 110px; align-items: start; }
  .ql.has-folder { grid-template-columns: 24px minmax(240px, 2fr) minmax(140px, 1fr) 110px 150px 170px 110px; }
  .ql code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ql__err { color: var(--b2s-color-danger-strong); font-size: var(--b2s-fs-xs); }
  .ql__note { color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-xs); }
  .ql__ok { display: inline-flex; gap: 4px; align-items: center; color: var(--b2s-color-success-strong); font-size: var(--b2s-fs-xs); }
</style>
