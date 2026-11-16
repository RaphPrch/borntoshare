<script lang="ts">
  import { t } from '$lib/i18n';
  import { setCrumbs } from '$lib/stores/crumbs';

  /**
   * One sheet per scanned folder: its name and place, then its tabs (content, 5S workshop, duplicates, rights to
   * review, report). Each tab is a page of its own; the header makes them read as one.
   */
  type Tab = 'content' | 'workshop' | 'duplicates' | 'access' | 'report';
  interface Props {
    rootId: number;
    name: string;
    path?: string;
    current: Tab;
    counts?: Partial<Record<Tab, number>>;
    actions?: import('svelte').Snippet;
  }

  let { rootId, name, path = '', current, counts = {}, actions }: Props = $props();
  let tabs = $derived([
    { key: 'content', label: t('Content'), href: `/five-s/explore/${rootId}` },
    { key: 'workshop', label: t('5S workshop'), href: `/five-s/explore/${rootId}?view=workshop` },
    { key: 'duplicates', label: t('Duplicates'), href: `/five-s/duplicates/${rootId}` },
    { key: 'access', label: t('Rights to review'), href: `/five-s/access/${rootId}` },
    { key: 'report', label: t('Report'), href: `/five-s/report/${rootId}` }
  ] as Array<{ key: Tab; label: string; href: string }>);
  // The top bar says where: Explorer › <folder> › <tab>
  $effect(() => setCrumbs([{ label: name, href: `/five-s/explore/${rootId}` }, { label: tabs.find((tab) => tab.key === current)?.label ?? '' }]));
</script>

<header class="ffh">
  <a class="ffh__back" href="/five-s/explore"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the folders')}</a>
  <div class="v2-head">
    <div>
      <h1>{name || '…'}</h1>
      {#if path}<p class="ffh__path"><code data-copy={path}>{path}</code></p>{/if}
    </div>
    {#if actions}<div class="v2-head__act">{@render actions()}</div>{/if}
  </div>
  <nav class="v2-tabs" aria-label={t('Sheet of the folder')}>
    {#each tabs as tab (tab.key)}
      <a href={tab.href} class:is-on={tab.key === current} aria-current={tab.key === current ? 'page' : undefined}>
        {tab.label}{#if counts[tab.key]}<b>{counts[tab.key]}</b>{/if}</a>
    {/each}
  </nav>
</header>

<style>
  .ffh { display: grid; gap: 10px; }
  .ffh__back { display: inline-flex; gap: 6px; align-items: center; width: fit-content; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); text-decoration: none; }
  .ffh__back:hover { color: var(--b2s-color-text); }
  .ffh__path { margin: 2px 0 0; }
  .ffh__path code { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
