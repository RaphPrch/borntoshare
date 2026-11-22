<script module lang="ts">
  import { t } from '$lib/i18n';

  /** What the 5S scanner says of a measure: complete, partial (the inventory misses something) or sampled (the duplicates are an estimate). */
  export type Completeness = {
    status: 'complete' | 'partial' | 'sampled';
    reasons: Array<{ code: string; count: number; pieces: string[] }>;
    acl_orphan_entries?: number;
    cut_paths?: Array<{ path: string; deep: boolean }>;
  };

  export const COMPLETENESS_LABEL = (): Record<string, string> => ({
    complete: t('Complete inventory'), partial: t('Partial inventory'), sampled: t('Sampled duplicates')
  });

  /** One plain sentence per reason */
  export function reasonText(reason: { code: string; count: number }): string {
    const texts: Record<string, string> = {
      FILES_LIST_CUT: t('File list cut: more than 300,000 files in {count} part(s), the explorer does not show them all'),
      DIRS_CUT: t('More than 50,000 folders in {count} part(s): the tree is incomplete there'),
      ACLS_CUT: t('Rights of more than 50,000 folders in {count} part(s): not all kept'),
      ACL_UNREADABLE: t('Rights of {count} folder(s) could not be read'),
      DENIED_FOLDERS: t('{count} folder(s) could not be opened (access refused): their content is not counted'),
      UNREADABLE_PIECES: t('{count} part(s) unreadable: their previous measure is kept'),
      DUPLICATES_SAMPLED: t('Duplicates searched among part of the same-size files only ({count} part(s))'),
      FINGERPRINTS_PENDING: t('Fingerprints not all computed yet ({count} part(s)): duplicates are provisional')
    };
    return texts[reason.code] ?? reason.code;
  }
</script>

<script lang="ts">
  /**
   * The state of the last measure of a folder: a pill (compact), or the pill with every reason in plain words.
   * What the scanner could not see is always shown, never presented as complete.
   */
  interface Props {
    value: Completeness | null | undefined;
    compact?: boolean;
  }

  let { value, compact = false }: Props = $props();

  const TONE: Record<string, string> = { complete: 'ok', partial: 'warn', sampled: 'info' };
  const ICON: Record<string, string> = { complete: 'bi-check2-circle', partial: 'bi-exclamation-triangle', sampled: 'bi-pie-chart' };
  let reasons = $derived(value?.reasons ?? []);
  let summary = $derived(reasons.map(reasonText).join('\n'));
</script>

{#if value}
  {#if compact}
    <span class={`v2-tag is-${TONE[value.status] ?? 'mut'}`} title={summary || undefined}>
      <i class={`bi ${ICON[value.status] ?? 'bi-question-circle'}`} aria-hidden="true"></i> {COMPLETENESS_LABEL()[value.status] ?? value.status}
    </span>
  {:else if value.status !== 'complete' || value.acl_orphan_entries}
    <div class={`mc mc--${value.status}`} role="status">
      <i class={`bi ${ICON[value.status] ?? 'bi-info-circle'}`} aria-hidden="true"></i>
      <div>
        <b>{value.status === 'partial' ? t('This inventory is partial') : value.status === 'sampled' ? t('Duplicates are an estimate') : t('Complete inventory')}</b>
        <ul>
          {#each reasons as reason (reason.code)}
            <li>{reasonText(reason)}{#if reason.pieces.length}<small> — {reason.pieces.slice(0, 4).join(', ')}{reason.pieces.length > 4 ? '…' : ''}</small>{/if}</li>
          {/each}
          {#if value.acl_orphan_entries}
            <li>{t('{count} right(s) given to accounts deleted from the directory (orphan SIDs)', { count: value.acl_orphan_entries })}</li>
          {/if}
        </ul>
      </div>
    </div>
  {/if}
{/if}

<style>
  .mc { display: flex; gap: 12px; padding: 12px 14px; border: 1px solid; border-radius: 12px; font-size: var(--b2s-fs-sm); }
  .mc > i { font-size: 18px; line-height: 1.2; }
  .mc b { display: block; margin-bottom: 4px; }
  .mc ul { margin: 0; padding-left: 18px; display: grid; gap: 2px; }
  .mc small { color: var(--b2s-color-text-muted); }
  .mc--partial { border-color: var(--b2s-color-warning-border); background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .mc--sampled { border-color: var(--b2s-accent-border); background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
  .mc--complete { border-color: var(--b2s-color-border); background: var(--b2s-color-surface); }
</style>
