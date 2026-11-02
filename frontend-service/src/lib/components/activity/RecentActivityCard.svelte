<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import { formatActivityItem } from '$lib/activity/format';

  /** The last events of an entity in a card, with a link to its full history. */
  export let items: any[] = [];
  export let limit = 5;
  export let emptyLabel = t('No activity yet.');
  export let onOpenHistory: (() => void) | null = null;

  $: recent = items.slice(0, limit).map((entry) => ({ entry, item: formatActivityItem(entry) }));
</script>

<section class="rac" aria-label={t('Recent activity')}>
  <header>
    <h2>{t('Recent activity')}</h2>
    {#if onOpenHistory}<button type="button" on:click={onOpenHistory}>{t('All the history')} ›</button>{/if}
  </header>
  {#if recent.length}
    <ul>
      {#each recent as { entry, item }, index (index)}
        <li>
          <span class={`rac__dot is-${item.variant}`} aria-hidden="true"></span>
          <span class="rac__text"><strong>{item.title}</strong>{#if item.subtitle1}<small>{item.subtitle1}</small>{/if}</span>
          <small class="rac__when">{entry?.created_at ? timeAgo(String(entry.created_at)) : ''}</small>
        </li>
      {/each}
    </ul>
  {:else}
    <p>{emptyLabel}</p>
  {/if}
</section>

<style>
  .rac { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  header { display: flex; align-items: center; gap: 12px; }
  h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  header button { padding: 0; border: 0; background: none; color: var(--b2s-color-info-strong); font: inherit; font-size: var(--b2s-fs-sm); cursor: pointer; }
  ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
  li { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; gap: 10px; align-items: start; }
  p { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .rac__dot { width: 9px; height: 9px; margin-top: 6px; border-radius: 50%; background: var(--b2s-color-border-mid, #cdd2db); }
  .rac__dot.is-ok { background: var(--b2s-color-success); }
  .rac__dot.is-warn { background: var(--b2s-color-warning); }
  .rac__text { display: flex; flex-direction: column; min-width: 0; }
  .rac__text strong { font-weight: 500; font-size: var(--b2s-fs-sm); }
  .rac__text small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .rac__when { color: var(--b2s-color-text-soft); font-size: var(--b2s-fs-xs); white-space: nowrap; }
</style>
