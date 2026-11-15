<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiGetData } from '$lib/api/client';
  import { fivesEnabled } from '$lib/utils/features';
  import { formatBytes } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';

  /**
   * Explorer, entry: the measured folders by zone and server on the left, the folders of the scope on the right.
   * A folder opens its explorer (tree, files, duplicates, rights). Right click: its actions.
   */
  type Folder = { id: number; name: string; path: string; server: string; zone: string; size_bytes: number | null; score: number | null };

  let folders = $state<Folder[]>([]);
  let loading = $state(true);
  let error = $state('');
  let query = $state('');
  let open = $state<Record<string, boolean>>({});
  let scope = $state<{ zone?: string; server?: string }>({});

  onMount(async () => {
    if (!$fivesEnabled) {
      loading = false;
      error = t('The 5S module is not active.');
      return;
    }
    try {
      const data = await apiGetData<{ folders: Folder[] }>(fetch, '/modules/fives/five-s');
      folders = data?.folders ?? [];
      const first = folders[0]?.zone;
      if (first) open = { [`z:${first}`]: true };
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the 5S.');
    } finally {
      loading = false;
    }
  });

  let needle = $derived(query.trim().toLowerCase());
  let matching = $derived(folders.filter((f) => !needle || `${f.name} ${f.path} ${f.server} ${f.zone}`.toLowerCase().includes(needle)));
  let zones = $derived([...new Set(matching.map((f) => f.zone || '—'))].sort((a, b) => a.localeCompare(b)));
  const serversOf = (zone: string) => [...new Set(matching.filter((f) => (f.zone || '—') === zone).map((f) => f.server || '—'))].sort((a, b) => a.localeCompare(b));
  const foldersOf = (zone: string, server: string) => matching.filter((f) => (f.zone || '—') === zone && (f.server || '—') === server);
  let shown = $derived(
    matching
      .filter((f) => (!scope.zone || (f.zone || '—') === scope.zone) && (!scope.server || (f.server || '—') === scope.server))
      .slice()
      .sort((a, b) => (b.size_bytes ?? 0) - (a.size_bytes ?? 0))
  );
  let maxSize = $derived(Math.max(1, ...shown.map((f) => f.size_bytes ?? 0)));
  const tone = (score: number | null) => (score == null ? 'mut' : score >= 80 ? 'ok' : score >= 60 ? 'warn' : 'bad');

  // ---- right click ----
  let menu = $state<{ folder: Folder; at: { x: number; y: number } } | null>(null);
  const menuItems: ContextMenuItem[] = [
    { key: 'explore', label: t('Explore'), icon: 'bi-columns-gap' },
    { key: 'report', label: t('5S report'), icon: 'bi-file-earmark-bar-graph' },
    { key: 'duplicates', label: t('Duplicates'), icon: 'bi-files' },
    { key: 'root', label: t('Open the folder sheet'), icon: 'bi-folder2-open', separated: true }
  ];
  function onPick(key: string) {
    const id = menu?.folder.id;
    if (!id) return;
    if (key === 'explore') void goto(`/five-s/explore/${id}`);
    if (key === 'report') void goto(`/five-s/report/${id}`);
    if (key === 'duplicates') void goto(`/five-s/duplicates/${id}`);
    if (key === 'root') void goto(`/storage-roots?selected=${id}`);
  }
  const openMenu = (folder: Folder) => (event: MouseEvent) => {
    event.preventDefault();
    menu = { folder, at: menuPositionFor(event) };
  };
</script>

<section class="v2">
  <div class="v2-head">
    <div>
      <h1>Explorer</h1>
      <p>{t('The inventoried content of the folders, and what the 5S knows about it. Choose a folder in the tree; right click: its actions.')}</p>
    </div>
  </div>

  {#if loading}
    <LoadingState />
  {:else if error}
    <InlineAlert tone="warning">{error}</InlineAlert>
  {:else}
    <div class="v2-ws">
      <aside class="v2-pane" aria-label={t('Folders')}>
        <h3>{t('Folders')}</h3>
        <label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Filter the tree…')} aria-label={t('Filter the tree')} /></label>
        <div>
          <button type="button" class="v2-trow" class:is-on={!scope.zone} onclick={() => (scope = {})}>
            <span class="v2-trow__car"></span><span class="v2-trow__l">{t('All the folders')}</span><span class="v2-trow__n">{matching.length}</span>
          </button>
          {#each zones as zone (zone)}
            {@const zOpen = needle !== '' || open[`z:${zone}`]}
            <button type="button" class="v2-trow" class:is-on={scope.zone === zone && !scope.server} aria-expanded={zOpen}
              onclick={() => { open = { ...open, [`z:${zone}`]: !(scope.zone === zone && !scope.server && zOpen) }; scope = { zone }; }}>
              <span class="v2-trow__car">{zOpen ? '▾' : '▸'}</span><span class="v2-trow__l">{zone}</span><span class="v2-trow__n">{matching.filter((f) => (f.zone || '—') === zone).length}</span>
            </button>
            {#if zOpen}
              {#each serversOf(zone) as server (server)}
                {@const sOpen = needle !== '' || open[`s:${zone}:${server}`]}
                <button type="button" class="v2-trow" style="padding-left: 22px" class:is-on={scope.server === server && scope.zone === zone} aria-expanded={sOpen}
                  onclick={() => { open = { ...open, [`s:${zone}:${server}`]: !(scope.server === server && sOpen) }; scope = { zone, server }; }}>
                  <span class="v2-trow__car">{sOpen ? '▾' : '▸'}</span><span class="v2-trow__l">{server}</span><span class="v2-trow__n">{foldersOf(zone, server).length}</span>
                </button>
                {#if sOpen}
                  {#each foldersOf(zone, server) as folder (folder.id)}
                    <a class="v2-trow" style="padding-left: 38px" href={`/five-s/explore/${folder.id}`} oncontextmenu={openMenu(folder)}>
                      <span class={`v2-dw is-${tone(folder.score)}`} aria-hidden="true"></span><span class="v2-trow__l">{folder.name}</span>
                      <span class="v2-trow__n">{folder.size_bytes != null ? formatBytes(folder.size_bytes) : ''}</span>
                    </a>
                  {/each}
                {/if}
              {/each}
            {/if}
          {/each}
        </div>
      </aside>

      <div class="v2-main">
        <div class="v2-tool">
          <div class="v2-scope">{scope.server ?? scope.zone ?? t('All the folders')}<small>{t('{count} folder(s)', { count: shown.length })}</small></div>
        </div>
        <div class="v2-list">
          <div class="v2-row is-head ex-grid"><span>{t('Folder')}</span><span>{t('Server')}</span><span>{t('Volume')}</span><span>5S</span><span></span></div>
          {#each shown as folder (folder.id)}
            <div class="v2-row ex-grid" role="row" tabindex="-1" oncontextmenu={openMenu(folder)}>
              <div class="v2-nm"><a href={`/five-s/explore/${folder.id}`}>{folder.name}</a><small>{folder.path}</small></div>
              <div class="v2-nm"><span>{folder.server}</span><span class="v2-sub">{folder.zone}</span></div>
              <div class="ex-vol"><span>{folder.size_bytes != null ? formatBytes(folder.size_bytes) : '—'}</span>
                <div class="v2-bar"><i style={`width: ${Math.max(3, Math.round(((folder.size_bytes ?? 0) / maxSize) * 100))}%`}></i></div></div>
              <span class={`v2-tag is-${tone(folder.score)}`}>{folder.score ?? '—'}</span>
              <button type="button" class="v2-dots" aria-label={t('Actions on {name}', { name: folder.name })} onclick={openMenu(folder)}><i class="bi bi-three-dots" aria-hidden="true"></i></button>
            </div>
          {:else}
            <div class="v2-empty">{t('No measured folder here yet.')}</div>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</section>

<ContextMenu open={menu != null} title={menu?.folder.name ?? ''} subtitle={menu?.folder.path ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  .ex-grid { grid-template-columns: minmax(220px, 2fr) minmax(140px, 1fr) 160px 60px 36px; min-width: 760px; }
  .ex-vol { display: flex; flex-direction: column; gap: 5px; font-size: 13px; font-weight: 500; }
  .ex-vol .v2-bar { height: 5px; }
</style>
