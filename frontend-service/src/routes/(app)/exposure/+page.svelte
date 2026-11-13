<script lang="ts">

  import { recall, remember } from '$lib/utils/remember';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';

  /**
   * Exposure map: every governed folder by zone, server and share, coloured by how widely its last ACL read opens it.
   * The colour is never alone: each tile has its icon and its name; a click opens the Permissions tab of the folder.
   */
  type Level = 'open_write' | 'open_read' | 'outside' | 'governed' | 'unknown';
  type Folder = { id: number; name: string; path: string; level: Level; broad: Array<{ principal: string; rights: string; write: boolean; inherited: boolean }>; outside_count: number; scanned_at: string | null };
  type Exposure = {
    summary: Record<Level, number> & { total: number };
    zones: Array<{ zone_id: number; zone: string; servers: Array<{ endpoint_id: number; server: string; shares: Array<{ share: string; folders: Folder[] }> }> }>;
  };

  const LEVELS: Array<{ key: Level; label: () => string; hint: () => string; icon: string }> = [
    { key: 'open_write', label: () => t('Open to everyone, in modify'), hint: () => t('Everyone, Users or Domain users can change the content'), icon: 'bi-unlock-fill' },
    { key: 'open_read', label: () => t('Open to everyone, in read'), hint: () => t('Everyone, Users or Domain users can read the content'), icon: 'bi-eye-fill' },
    { key: 'outside', label: () => t('Accounts outside BornToShare'), hint: () => t('Accounts or groups set directly on the file server'), icon: 'bi-person-exclamation' },
    { key: 'governed', label: () => t('Governed'), hint: () => t('Only its AD groups and the expected system accounts'), icon: 'bi-shield-check' },
    { key: 'unknown', label: () => t('Not read yet'), hint: () => t('No ACL read for this folder yet'), icon: 'bi-question-circle' }
  ];
  const meta = (level: Level) => LEVELS.find((entry) => entry.key === level) ?? LEVELS[4];

  let data = $state<Exposure | null>(null);
  let error = $state('');
  const savedExposure = recall('exposure', { filter: 'all', zoneFilter: 0 });
  let filter = $state(savedExposure.filter as Level | 'all');
  let zoneFilter = $state(savedExposure.zoneFilter);
  $effect.pre(() => {
    remember('exposure', { filter, zoneFilter });
  });
  let query = $state('');

  onMount(async () => {
    try {
      data = await apiGetData<Exposure>(fetch, '/storage-roots/exposure');
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the exposure map.');
    }
  });

  let needle = $derived(query.trim().toLowerCase());
  const keep = (folder: Folder, level: Level | 'all', text: string) =>
    (level === 'all' || folder.level === level) && (!text || `${folder.name} ${folder.path}`.toLowerCase().includes(text));
  // Zones, servers and shares without a folder left after the filters are hidden; the worst folders come first
  const ORDER: Level[] = ['open_write', 'open_read', 'outside', 'unknown', 'governed'];
  let zones = $derived((data?.zones ?? [])
    .filter((zone) => !zoneFilter || zone.zone_id === zoneFilter)
    .map((zone) => ({
      ...zone,
      servers: zone.servers
        .map((server) => ({
          ...server,
          shares: server.shares
            .map((share) => ({ ...share, folders: share.folders.filter((folder) => keep(folder, filter, needle)).sort((a, b) => ORDER.indexOf(a.level) - ORDER.indexOf(b.level) || a.name.localeCompare(b.name, 'fr', { numeric: true })) }))
            .filter((share) => share.folders.length)
        }))
        .filter((server) => server.shares.length)
    }))
    .filter((zone) => zone.servers.length));
  let total = $derived(data?.summary.total ?? 0);
  let atRisk = $derived((data?.summary.open_write ?? 0) + (data?.summary.open_read ?? 0));

  const counts = (folders: Folder[]) => ORDER.map((level) => ({ level, count: folders.filter((folder) => folder.level === level).length })).filter((entry) => entry.count);
  const tileTitle = (folder: Folder) =>
    [
      folder.path,
      meta(folder.level).label(),
      ...folder.broad.map((entry) => `${entry.principal} · ${entry.write ? t('modify') : t('read')}${entry.inherited ? ` (${t('inherited')})` : ''}`),
      folder.outside_count ? t('{count} account(s) outside BornToShare', { count: folder.outside_count }) : ''
    ].filter(Boolean).join('\n');
</script>

<svelte:head><title>{t('Exposure map')} · BornToShare</title></svelte:head>

<section class="ex">
  <header class="ex__top">
    <div>
      <h1>{t('Exposure map')}</h1>
      <p>{t('How widely each governed folder is open, from the last reading of its rights on the file server.')}</p>
    </div>
    {#if data}
      <div class="ex__score" class:is-bad={atRisk > 0}>
        <b>{total ? Math.round(((total - atRisk) / total) * 100) : 100}%</b>
        <span>{t('of the folders are not open to everyone')}</span>
      </div>
    {/if}
  </header>

  {#if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !data}
    <div class="ex__panel"><LoadingState skeleton="rows" rows={6}>{t('Reading the rights of the folders…')}</LoadingState></div>
  {:else}
    <div class="b2s-stat-tiles ex__tiles">
      {#each LEVELS as level (level.key)}
        <button type="button" class="b2s-stat-tile ex__tile is-{level.key}" class:is-on={filter === level.key} aria-pressed={filter === level.key} onclick={() => (filter = filter === level.key ? 'all' : level.key)}>
          <span class="ex__tile-head"><i class="bi {level.icon}" aria-hidden="true"></i>{level.label()}</span>
          <b><CountUp value={Number(data.summary[level.key] ?? 0)} /></b>
          <small>{level.hint()}</small>
        </button>
      {/each}
    </div>
    <div class="ex__bar" role="img" aria-label={LEVELS.map((level) => `${level.label()} : ${data?.summary[level.key] ?? 0}`).join(', ')}>
      {#each ORDER as level}{#if data.summary[level]}<i class="is-{level}" style="flex:{data.summary[level]}"></i>{/if}{/each}
    </div>

    <div class="ex__filters">
      <label class="ex__search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Filter by folder name or path')} aria-label={t('Filter by folder name or path')} /></label>
      {#if data.zones.length > 1}
        <select class="b2s-input ex__zone" bind:value={zoneFilter} aria-label={t('Zone')}>
          <option value={0}>{t('All zones')}</option>
          {#each data.zones as zone (zone.zone_id)}<option value={zone.zone_id}>{zone.zone}</option>{/each}
        </select>
      {/if}
      {#if filter !== 'all'}<button type="button" class="b2s-link-btn" onclick={() => (filter = 'all')}>{t('Show every level')}</button>{/if}
    </div>

    {#each zones as zone (zone.zone_id)}
      <section class="ex__zone-block" aria-label={zone.zone}>
        <h2><i class="bi bi-geo-alt" aria-hidden="true"></i>{zone.zone}</h2>
        {#each zone.servers as server (server.endpoint_id)}
          <div class="ex__server">
            <h3><i class="bi bi-hdd-network" aria-hidden="true"></i>{server.server}</h3>
            <div class="ex__shares">
              {#each server.shares as share (share.share)}
                <article class="ex__share">
                  <header>
                    <code title={share.share}>{share.share}</code>
                    <span class="ex__counts">
                      {#each counts(share.folders) as entry (entry.level)}<span class="is-{entry.level}" title={meta(entry.level).label()}><i class="bi {meta(entry.level).icon}" aria-hidden="true"></i>{entry.count}</span>{/each}
                    </span>
                  </header>
                  <div class="ex__grid">
                    {#each share.folders as folder (folder.id)}
                      <a class="ex__cell is-{folder.level}" href={`/storage-roots?selected=${folder.id}&tab=permissions`} title={tileTitle(folder)}>
                        <i class="bi {meta(folder.level).icon}" aria-hidden="true"></i>
                        <span>{folder.name}</span>
                        <span class="b2s-visually-hidden">{meta(folder.level).label()}</span>
                      </a>
                    {/each}
                  </div>
                </article>
              {/each}
            </div>
          </div>
        {/each}
      </section>
    {:else}
      <EmptyStateInline message={t('No folder matches these filters.')} actionLabel={filter !== 'all' || zoneFilter || query ? t('Clear the filters') : null} actionIcon="bi-x-circle" onAction={() => { filter = 'all'; zoneFilter = 0; query = ''; }} />
    {/each}
  {/if}
</section>

<style>
  .ex { padding: var(--b2s-page-padding, 24px 28px); display: flex; flex-direction: column; gap: 16px; }
  .ex__top { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
  .ex__top h1 { margin: 0; font-size: var(--b2s-fs-overview-title, 38px); line-height: 1.05; font-weight: 600; letter-spacing: -0.03em; }
  .ex__top p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .ex__score { display: flex; flex-direction: column; align-items: flex-end; }
  .ex__score b { font-size: 28px; font-weight: 700; color: var(--b2s-color-success-strong); line-height: 1; }
  .ex__score.is-bad b { color: var(--b2s-color-danger-strong); }
  .ex__score span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ex__panel { padding: 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ex__tiles { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .ex__tile { text-align: left; }
  .ex__tile.is-on { border-color: var(--b2s-color-text); box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
  .ex__tile-head { display: flex; align-items: center; gap: 6px; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text-muted); }
  .ex__tile b { display: block; margin: 4px 0; font-size: 26px; font-weight: 700; }
  .ex__tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ex__tile.is-open_write .ex__tile-head i { color: var(--b2s-color-danger-strong); }
  .ex__tile.is-open_read .ex__tile-head i { color: var(--b2s-color-warning-strong); }
  .ex__tile.is-outside .ex__tile-head i { color: var(--b2s-color-info-strong); }
  .ex__tile.is-governed .ex__tile-head i { color: var(--b2s-color-success-strong); }
  .ex__bar { display: flex; gap: 2px; height: 10px; border-radius: var(--b2s-radius-pill); overflow: hidden; background: var(--b2s-color-surface); }
  .ex__bar i { display: block; min-width: 4px; }
  .ex__filters { display: flex; align-items: center; gap: 10px; }
  .ex__search { flex: 1; display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .ex__search input { flex: 1; border: 0; outline: 0; background: none; font: inherit; }
  .ex__zone { width: auto; }
  .ex__zone-block { display: flex; flex-direction: column; gap: 10px; }
  .ex__zone-block h2 { display: flex; align-items: center; gap: 8px; margin: 8px 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ex__server h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: var(--b2s-fs-sm); font-weight: 600; color: var(--b2s-color-text-muted); }
  .ex__shares { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
  .ex__share { display: flex; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ex__share header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .ex__share code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .ex__counts { display: flex; gap: 6px; flex: none; }
  .ex__counts span { display: inline-flex; align-items: center; gap: 3px; font-size: var(--b2s-fs-xs); font-weight: 600; }
  .ex__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; }
  .ex__cell { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--b2s-radius-sm); font-size: var(--b2s-fs-xs); font-weight: 500; color: var(--b2s-color-text); text-decoration: none; transition: transform 0.12s ease, box-shadow 0.12s ease; }
  .ex__cell span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ex__cell:hover, .ex__cell:focus-visible { transform: translateY(-1px); box-shadow: var(--b2s-shadow-sm); border-color: var(--b2s-color-text); }
  .is-open_write { --ex-bg: var(--b2s-color-danger-soft); --ex-fg: var(--b2s-color-danger-strong); }
  .is-open_read { --ex-bg: var(--b2s-color-warning-soft); --ex-fg: var(--b2s-color-warning-strong); }
  .is-outside { --ex-bg: var(--b2s-color-info-soft); --ex-fg: var(--b2s-color-info-strong); }
  .is-governed { --ex-bg: var(--b2s-color-success-soft); --ex-fg: var(--b2s-color-success-strong); }
  .is-unknown { --ex-bg: var(--b2s-color-neutral-soft); --ex-fg: var(--b2s-color-text-muted); }
  .ex__cell { background: var(--ex-bg); }
  .ex__cell i, .ex__counts span { color: var(--ex-fg); }
  .ex__bar i { background: var(--ex-fg); }
</style>
