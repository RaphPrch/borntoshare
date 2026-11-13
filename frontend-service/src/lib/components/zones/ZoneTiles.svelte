<script lang="ts">
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import { t } from '$lib/i18n';
  import type { ZoneSummary } from './zone-summary';

  
  interface Props {
    /** The figures of a zone as four tiles: servers reachable, folders to review, pending requests, guardians. */
    summary: ZoneSummary;
    pendingRequests?: number;
    onOpenServers?: () => void;
    onOpenFolders?: () => void;
    onOpenRequests?: () => void;
    onOpenGuardians?: () => void;
  }

  let {
    summary,
    pendingRequests = 0,
    onOpenServers = () => {},
    onOpenFolders = () => {},
    onOpenRequests = () => {},
    onOpenGuardians = () => {}
  }: Props = $props();

  let files = $derived(summary.files.length);
  let down = $derived(summary.unreachable.length);
  let roots = $derived(summary.roots.length);
  let review = $derived(summary.review.length);
</script>

<section class="b2s-stat-tiles" aria-label={t('Zone summary')}>
  <button type="button" class="b2s-stat-tile" onclick={onOpenServers}>
    <span>{t('Servers reachable')}</span>
    <b class:is-bad={down > 0}>{files ? `${summary.reachable} / ${files}` : '—'}</b>
    <small>
      {down ? t('{count} unreachable', { count: down }) : files ? t('all answer') : t('No file server yet')}{summary.dfs.length ? ` · ${t('+ {count} DFS namespace(s)', { count: summary.dfs.length })}` : ''}
    </small>
    {#if files}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${summary.reachable}`}></i><i class="bad" style={`flex:${down}`}></i><i class="mute" style={`flex:${files - summary.reachable - down}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" onclick={onOpenFolders}>
    <span>{t('Managed folders')}</span>
    <b><CountUp value={Number(roots)} /></b>
    <small>{review ? t('{count} to review', { count: review }) : roots ? t('all in order') : t('No managed folder')}</small>
    {#if roots}<span class="b2s-stat-bar" aria-hidden="true"><i style={`flex:${roots - review}`}></i><i class="warn" style={`flex:${review}`}></i></span>{/if}
  </button>
  <button type="button" class="b2s-stat-tile" onclick={onOpenRequests}>
    <span>{t('Pending requests')}</span>
    <b class:is-warn={pendingRequests > 0}><CountUp value={Number(pendingRequests)} /></b>
    <small>{pendingRequests ? t('to decide by the guardians') : t('nothing to decide')}</small>
  </button>
  <button type="button" class="b2s-stat-tile" onclick={onOpenGuardians}>
    <span>{t('Without guardian')}</span>
    <b class:is-warn={summary.noGuardian.length > 0}><CountUp value={Number(summary.noGuardian.length)} /></b>
    <small>{t('the administrators decide on their requests')}</small>
  </button>
</section>

