<script lang="ts">
  import { t } from '$lib/i18n';
  import { crumbs } from '$lib/stores/crumbs';
  import { live } from '$lib/stores/live';
  import SectionTabs from './SectionTabs.svelte';
  import { activeItem, buildNav } from './nav';

  /**
   * Under the top bar: where you are (section › page › the crumbs a page sets) and, for an entry that gathers several
   * pages, their tabs. Always in view, so the menu never has to stay open.
   */
  interface Props {
    currentPath?: string;
    admin?: boolean;
    staff?: boolean;
    features?: string[];
  }

  let { currentPath = '', admin = false, staff = false, features = [] }: Props = $props();
  let here = $derived(activeItem(buildNav({ admin, staff, features, pending: $live.pending ?? 0, critical: $live.critical ?? 0 }), currentPath));
  let tabs = $derived(here?.item.tabs ?? []);
  // Not on the page it leads to (the form of a new request…)
  let action = $derived(here?.item.action && currentPath !== here.item.action.href ? here.item.action : null);
</script>

{#if here}
  <div class="cb">
    <nav class="cb__crumb" aria-label={t('Location')}>
      <span>{here.section.label}</span><i class="bi bi-chevron-right" aria-hidden="true"></i>
      {#if $crumbs.length}<a href={here.item.href}>{here.item.label}</a>{:else}<b>{here.item.label}</b>{/if}
      {#each $crumbs as crumb, index (index)}
        <i class="bi bi-chevron-right" aria-hidden="true"></i>
        {#if crumb.href && index < $crumbs.length - 1}<a href={crumb.href}>{crumb.label}</a>{:else}<b>{crumb.label}</b>{/if}
      {/each}
    </nav>
    {#if tabs.length > 1}<div class="cb__tabs"><SectionTabs {tabs} label={here.item.label} /></div>{/if}
    {#if action}<a class="b2s-btn b2s-btn-primary b2s-btn-sm cb__action" href={action.href}><i class={`bi ${action.icon}`} aria-hidden="true"></i>{action.label}</a>{/if}
  </div>
{/if}

<style>
  .cb { position: sticky; top: 52px; z-index: 40; display: flex; flex-wrap: wrap; align-items: flex-end; gap: 4px 24px; min-height: 44px; padding: 0 24px;
    border-bottom: 1px solid var(--b2s-color-border-soft); background: var(--b2s-color-surface); }
  .cb__crumb { display: flex; align-items: center; gap: 6px; min-width: 0; height: 44px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .cb__crumb i { font-size: 10px; }
  .cb__crumb b { color: var(--b2s-color-text); font-weight: 600; white-space: nowrap; }
  .cb__crumb a { color: inherit; text-decoration: none; white-space: nowrap; }
  .cb__crumb a:hover { color: var(--b2s-color-text); text-decoration: underline; }
  .cb__action { align-self: center; margin-left: auto; }
  /* The tabs sit on the bottom line of the bar */
  .cb__tabs :global(.v2-tabs) { margin: 0; border-bottom: 0; }
</style>
