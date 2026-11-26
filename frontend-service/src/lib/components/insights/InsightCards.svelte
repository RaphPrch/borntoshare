<script lang="ts">
  /**
   * The recommendations as figure cards (value, meaning, share of the folders concerned): a click lists the folders
   * (the express search of Storage Roots), a right click offers the actions. Recommendations tab, and the first ones on
   * the Overview of Insights & Recommendations.
   */
  import { goto } from '$app/navigation';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { t } from '$lib/i18n';
  import { copyText } from '$lib/utils/clipboard';
  import { INSIGHT_ICONS, type Insight } from '$lib/utils/insights';

  interface Props {
    insights: Insight[];
    /** Folders read: the share of each card */
    total: number;
    isAdmin?: boolean;
  }
  let { insights, total, isAdmin = false }: Props = $props();

  const openFolders = (insight: Insight) => goto(`/storage-roots?q=${encodeURIComponent(insight.query)}`);
  let menu = $state<{ insight: Insight; at: { x: number; y: number } } | null>(null);
  let menuItems = $derived<ContextMenuItem[]>([
    { key: 'folders', label: t('See the folders concerned'), icon: 'bi-folder2-open' },
    ...(isAdmin ? [{ key: 'policy', label: t('Make a policy of it'), icon: 'bi-lightning-charge' }] : []),
    { key: 'copy', label: t('Copy the search'), icon: 'bi-clipboard', separated: true }
  ]);
  async function onPick(key: string) {
    const insight = menu?.insight;
    if (!insight) return;
    if (key === 'folders') void openFolders(insight);
    if (key === 'policy') void goto('/policies');
    if (key === 'copy') await copyText(insight.query);
  }
</script>

<div class="rp__kpis">
        {#each insights as insight (insight.key)}
          {@const share = total ? Math.max(2, Math.round((insight.count / total) * 100)) : 0}
          <button type="button" class={`rp__kpi is-${insight.tone}`} onclick={() => openFolders(insight)}
            oncontextmenu={(event) => { event.preventDefault(); menu = { insight, at: menuPositionFor(event) }; }}>
            <span class="rp__kpi-head"><span class="rp__kpi-title">{insight.title}</span><i class={`bi ${INSIGHT_ICONS[insight.key] ?? 'bi-lightbulb'}`} aria-hidden="true"></i></span>
            <b class="rp__big">{insight.big}</b>
            <small>{insight.detail}</small>
            <span class="rp__share" title={t('{count} folder(s) out of {total}', { count: insight.count, total })}>
              <span class="rp__bar"><i style={`width: ${share}%`}></i></span>
              <span>{t('{count} folder(s)', { count: insight.count })} <i class="bi bi-arrow-right" aria-hidden="true"></i></span>
            </span>
          </button>
        {/each}
      </div>

<ContextMenu open={menu != null} title={menu?.insight.title ?? ''} subtitle={menu?.insight.query ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  /* Recommendations as figures: value, meaning, and the share of the folders concerned */
  .rp__kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
  .rp__kpi { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px; border: 1px solid var(--b2s-color-border-soft); border-left: 3px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: border-color var(--b2s-motion-base) var(--b2s-ease-out), box-shadow var(--b2s-motion-base) var(--b2s-ease-out), transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .rp__kpi:hover { box-shadow: var(--b2s-shadow-md); transform: translateY(-1px); }
  .rp__kpi.is-bad { border-left-color: var(--b2s-color-danger); }
  .rp__kpi.is-warn { border-left-color: var(--b2s-color-warning); }
  .rp__kpi.is-mut { border-left-color: var(--b2s-color-border-strong); }
  .rp__kpi-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .rp__kpi-title { color: var(--b2s-color-text-soft); font-size: 13px; font-weight: 600; }
  .rp__kpi-head i { color: var(--b2s-color-text-faint); font-size: 16px; }
  .rp__kpi.is-bad .rp__kpi-head i { color: var(--b2s-color-danger); }
  .rp__kpi.is-warn .rp__kpi-head i { color: var(--b2s-color-warning); }
  .rp__big { color: var(--b2s-color-heading); font-size: 26px; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .rp__kpi small { flex: 1; color: var(--b2s-color-text-muted); font-size: 12px; line-height: 1.45; }
  .rp__share { display: grid; gap: 5px; color: var(--b2s-color-text-soft); font-size: 12px; font-weight: 600; }
  .rp__bar { height: 5px; overflow: hidden; border-radius: 999px; background: var(--b2s-color-surface-muted); }
  .rp__bar i { display: block; height: 100%; border-radius: 999px; background: var(--b2s-accent-vivid); transition: width var(--b2s-motion-slow) var(--b2s-ease-out); }
  .rp__kpi.is-bad .rp__bar i { background: var(--b2s-color-danger); }
  .rp__kpi.is-warn .rp__bar i { background: var(--b2s-color-warning); }
</style>
