<script lang="ts">
  import { recall, remember } from '$lib/utils/remember';
  import { fivesEnabled } from '$lib/utils/features';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiGetData } from '$lib/api/client';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { t } from '$lib/i18n';
  import { formatBytes } from '$lib/utils/format';

  /**
   * Analytics (v2): the 5S of the file shares, for the scope chosen in the tree on the left (all, a zone, a server,
   * one folder). The score and the five pillars as rings, the duplicates, what to do first, the folders least kept
   * first. Everything is computed from the scores of the folders of the scope.
   */
  type Pillar = 'sort' | 'order' | 'shine' | 'standard' | 'sustain';
  type Folder = { id: number; name: string; path: string; server: string; zone: string; size_bytes: number | null; score: number | null;
    pillars: Record<Pillar, number | null>; actions: Array<{ pillar: Pillar; text: string }> };
  type FiveS = { score: number | null; pillars: Record<Pillar, number | null>; folders_count: number; scope: string;
    top_actions: Array<{ pillar: Pillar; text: string; folders: number }>; folders: Folder[]; zones: Array<{ id: number; name: string }>;
    duplicates: { inside_bytes: number; between_bytes: number; folders_count: number; measured_on_server: number;
      folders: Array<{ id: number; name: string; inside: number; groups: number; shared: number; with: number }> } };

  const PILLARS: Array<{ key: Pillar; label: () => string; jp: string; hint: () => string }> = [
    { key: 'sort', label: () => t('5S: Sort'), jp: 'Seiri', hint: () => t('Keep what is used: data untouched for years goes to the archive, duplicates go.') },
    { key: 'order', label: () => t('5S: Set in order'), jp: 'Seiton', hint: () => t('Each folder has its owners and its place: guardians, a tag, a quota.') },
    { key: 'shine', label: () => t('5S: Shine'), jp: 'Seiso', hint: () => t('Nothing that should not be there: passwords, keys, clutter files.') },
    { key: 'standard', label: () => t('5S: Standardize'), jp: 'Seiketsu', hint: () => t('The folder follows the rule: inheritance, no error, reachable.') },
    { key: 'sustain', label: () => t('5S: Sustain'), jp: 'Shitsuke', hint: () => t('It is kept up: measured and scanned recently, requests and corrections handled.') }
  ];
  const label = (key: Pillar) => PILLARS.find((p) => p.key === key)?.label() ?? key;
  const tone = (score: number | null | undefined) => (score == null ? 'none' : score >= 80 ? 'ok' : score >= 60 ? 'warn' : 'bad');
  const COLOR = { ok: '#16a06a', warn: '#d97706', bad: '#dc3545', none: '#cdd2db' } as const;
  const verdict = (score: number | null | undefined) =>
    score == null ? t('Not enough data') : score >= 80 ? t('Well kept') : score >= 60 ? t('To improve') : t('To take in hand');

  let data = $state<FiveS | null>(null);
  let error = $state('');
  // The 5S is an optional module: switched off, the page says where to turn it on
  let disabled = $state(false);
  let pillarSort = $state(recall('five-s', { pillarSort: 'score' }).pillarSort as Pillar | 'score');
  $effect.pre(() => {
    remember('five-s', { pillarSort });
  });
  let query = $state('');
  let treeQuery = $state('');
  let shown = $state(30);
  let scope = $state<{ zone?: string; server?: string; folder?: number }>({});
  let open = $state<Record<string, boolean>>({});

  onMount(() => {
    if ($fivesEnabled) void load();
    else disabled = true;
  });
  async function load() {
    error = '';
    try {
      data = await apiGetData<FiveS>(fetch, '/modules/fives/five-s');
      const first = data?.folders?.[0]?.zone;
      if (first) open = { [`z:${first}`]: true };
    } catch (failure) {
      const code = (failure as { code?: string; status?: number })?.code;
      if (code === 'FEATURE_DISABLED' || (failure as { status?: number })?.status === 403) disabled = true;
      else error = failure instanceof Error ? failure.message : t('Unable to load the 5S.');
    }
  }

  // ---- the tree: zone > server > folder ----
  const zoneOf = (f: Folder) => f.zone || '—';
  const serverOf = (f: Folder) => f.server || '—';
  let treeNeedle = $derived(treeQuery.trim().toLowerCase());
  let treeFolders = $derived((data?.folders ?? []).filter((f) => !treeNeedle || `${f.name} ${f.server} ${f.zone}`.toLowerCase().includes(treeNeedle)));
  let zones = $derived([...new Set(treeFolders.map(zoneOf))].sort((a, b) => a.localeCompare(b, 'fr')));
  const serversOf = (zone: string) => [...new Set(treeFolders.filter((f) => zoneOf(f) === zone).map(serverOf))].sort((a, b) => a.localeCompare(b, 'fr'));
  const foldersOf = (zone: string, server: string) => treeFolders.filter((f) => zoneOf(f) === zone && serverOf(f) === server);
  const meanOf = (values: Array<number | null>) => {
    const known = values.filter((v): v is number => v != null);
    return known.length ? Math.round(known.reduce((a, b) => a + b, 0) / known.length) : null;
  };

  // ---- the scope and its figures ----
  let scoped = $derived((data?.folders ?? []).filter((f) =>
    scope.folder ? f.id === scope.folder : (!scope.zone || zoneOf(f) === scope.zone) && (!scope.server || serverOf(f) === scope.server)));
  let isAll = $derived(!scope.zone && !scope.server && !scope.folder);
  let score = $derived(isAll ? (data?.score ?? null) : meanOf(scoped.map((f) => f.score)));
  let pillars = $derived(Object.fromEntries(PILLARS.map((p) => [p.key, isAll ? (data?.pillars[p.key] ?? null) : meanOf(scoped.map((f) => f.pillars[p.key]))])) as Record<Pillar, number | null>);
  let scopeTitle = $derived(scope.folder ? (scoped[0]?.name ?? '') : scope.server ?? scope.zone ?? t('All the folders'));
  let scopeSize = $derived(scoped.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0));
  let scopedIds = $derived(new Set(scoped.map((f) => f.id)));
  let dupFolders = $derived((data?.duplicates.folders ?? []).filter((f) => scopedIds.has(f.id)));
  let dupInside = $derived(dupFolders.reduce((sum, f) => sum + f.inside, 0));
  let dupShared = $derived(dupFolders.reduce((sum, f) => sum + f.shared, 0));
  // What to do first: the actions of the folders of the scope, the most frequent first
  let topActions = $derived.by(() => {
    if (isAll) return data?.top_actions ?? [];
    const counts = new Map<string, { pillar: Pillar; text: string; folders: number }>();
    for (const folder of scoped) {
      for (const action of folder.actions) {
        const key = `${action.pillar}|${action.text}`;
        const entry = counts.get(key) ?? { ...action, folders: 0 };
        entry.folders += 1;
        counts.set(key, entry);
      }
    }
    return [...counts.values()].sort((a, b) => b.folders - a.folders).slice(0, 6);
  });
  let needle = $derived(query.trim().toLowerCase());
  let folders = $derived(scoped
    .filter((f) => !needle || `${f.name} ${f.path} ${f.server} ${f.zone}`.toLowerCase().includes(needle))
    .slice()
    .sort((a, b) => {
      const va = pillarSort === 'score' ? a.score : a.pillars[pillarSort];
      const vb = pillarSort === 'score' ? b.score : b.pillars[pillarSort];
      return (va ?? 101) - (vb ?? 101);
    }));
  const ring = (value: number | null, r: number) => {
    const c = 2 * Math.PI * r;
    return `${((c * (value ?? 0)) / 100).toFixed(1)} ${c.toFixed(1)}`;
  };

  // ---- right click on a folder ----
  let menu = $state<{ folder: Folder; at: { x: number; y: number } } | null>(null);
  const menuItems: ContextMenuItem[] = [
    { key: 'scope', label: t('5S of this folder'), icon: 'bi-bullseye' },
    { key: 'explore', label: t('Explore'), icon: 'bi-columns-gap' },
    { key: 'report', label: t('5S report'), icon: 'bi-file-earmark-bar-graph' },
    { key: 'duplicates', label: t('Duplicates'), icon: 'bi-files' },
    { key: 'root', label: t('Open the folder sheet'), icon: 'bi-folder2-open', separated: true }
  ];
  function onPick(key: string) {
    const folder = menu?.folder;
    if (!folder) return;
    if (key === 'scope') scope = { zone: zoneOf(folder), server: serverOf(folder), folder: folder.id };
    if (key === 'explore') void goto(`/five-s/explore/${folder.id}`);
    if (key === 'report') void goto(`/five-s/report/${folder.id}`);
    if (key === 'duplicates') void goto(`/five-s/duplicates/${folder.id}`);
    if (key === 'root') void goto(`/storage-roots?selected=${folder.id}`);
  }
  const openMenu = (folder: Folder) => (event: MouseEvent) => {
    event.preventDefault();
    menu = { folder, at: menuPositionFor(event) };
  };
</script>

<section class="v2 fs">
  <div class="v2-head">
    <div>
      <h1>Analytics</h1>
      <p>{t('The 5S of a zone, a server or a folder: choose it in the tree, everything is computed again.')}</p>
    </div>
  </div>

  {#if disabled}
    <div class="fs__off">
      <i class="bi bi-key" aria-hidden="true"></i>
      <div>
        <b>{t('The 5S module is not active')}</b>
        <p>{t('It is opened by a license key and switched on by an administrator in Advanced settings › Features; its databases are installed by the installation wizard.')}</p>
        <a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href="/admin/advanced-settings/features">{t('Open Features')}</a>
      </div>
    </div>
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !data}
    <LoadingState block skeleton="detail" />
  {:else if !data.folders_count}
    <EmptyStateInline message={t('No folder to score yet.')} actionLabel={t('Open the scanner')} href="/five-s/scanner" actionIcon="bi-broadcast" />
  {:else}
    <div class="v2-ws">
      <aside class="v2-pane" aria-label={t('Scope')}>
        <h3>{t('Scope')}</h3>
        <label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={treeQuery} placeholder={t('Filter the tree…')} aria-label={t('Filter the tree')} /></label>
        <div>
          <button type="button" class="v2-trow" class:is-on={isAll} onclick={() => (scope = {})}>
            <span class="v2-trow__car"></span><span class={`v2-dw is-${tone(data.score)}`}></span><span class="v2-trow__l">{t('All the folders')}</span><span class="v2-trow__n">{data.folders.length}</span>
          </button>
          {#each zones as zone (zone)}
            {@const zOpen = treeNeedle !== '' || open[`z:${zone}`]}
            {@const zScore = meanOf(data.folders.filter((f) => zoneOf(f) === zone).map((f) => f.score))}
            <button type="button" class="v2-trow" class:is-on={scope.zone === zone && !scope.server && !scope.folder} aria-expanded={zOpen}
              onclick={() => { open = { ...open, [`z:${zone}`]: !(scope.zone === zone && !scope.server && zOpen) }; scope = { zone }; }}>
              <span class="v2-trow__car">{zOpen ? '▾' : '▸'}</span><span class={`v2-dw is-${tone(zScore)}`}></span><span class="v2-trow__l">{zone}</span><span class="v2-trow__n">{zScore ?? '—'}</span>
            </button>
            {#if zOpen}
              {#each serversOf(zone) as server (server)}
                {@const sOpen = treeNeedle !== '' || open[`s:${zone}:${server}`]}
                {@const sScore = meanOf(foldersOf(zone, server).map((f) => f.score))}
                <button type="button" class="v2-trow" style="padding-left: 22px" class:is-on={scope.server === server && scope.zone === zone && !scope.folder} aria-expanded={sOpen}
                  onclick={() => { open = { ...open, [`s:${zone}:${server}`]: !(scope.server === server && !scope.folder && sOpen) }; scope = { zone, server }; }}>
                  <span class="v2-trow__car">{sOpen ? '▾' : '▸'}</span><span class={`v2-dw is-${tone(sScore)}`}></span><span class="v2-trow__l">{server}</span><span class="v2-trow__n">{sScore ?? '—'}</span>
                </button>
                {#if sOpen}
                  {#each foldersOf(zone, server) as folder (folder.id)}
                    <button type="button" class="v2-trow" style="padding-left: 38px" class:is-on={scope.folder === folder.id}
                      onclick={() => (scope = { zone, server, folder: folder.id })} oncontextmenu={openMenu(folder)}>
                      <span class="v2-trow__car"></span><span class={`v2-dw is-${tone(folder.score)}`}></span><span class="v2-trow__l">{folder.name}</span><span class="v2-trow__n">{folder.score ?? '—'}</span>
                    </button>
                  {/each}
                {/if}
              {/each}
            {/if}
          {/each}
        </div>
      </aside>

      <div class="v2-main fs__main">
        <div class="v2-scope">{scopeTitle}
          <small>{t('{count} folder(s)', { count: scoped.length })}{scopeSize ? ` · ${formatBytes(scopeSize)}` : ''} · {verdict(score)}</small></div>

        <div class="fs__rings">
          <div class="fs__big">
            <svg viewBox="0 0 140 140" role="img" aria-label={t('5S score: {score} out of 100', { score: score ?? '—' })}>
              <circle cx="70" cy="70" r="58" fill="none" stroke="#eef0f3" stroke-width="14" />
              <circle cx="70" cy="70" r="58" fill="none" stroke="#0e1218" stroke-width="14" stroke-linecap="round" stroke-dasharray={ring(score, 58)} class="fs__arc" />
            </svg>
            <span><b><CountUp value={score ?? 0} /></b><small>/ 100</small></span>
          </div>
          {#each PILLARS as pillar (pillar.key)}
            <button type="button" class="fs__pillar" class:is-on={pillarSort === pillar.key} aria-pressed={pillarSort === pillar.key}
              onclick={() => (pillarSort = pillarSort === pillar.key ? 'score' : pillar.key)} title={`${pillar.hint()} — ${t('Sort the folders by this pillar')}`}>
              <span class="fs__small">
                <svg viewBox="0 0 84 84" aria-hidden="true"><circle cx="42" cy="42" r="34" fill="none" stroke="#eef0f3" stroke-width="9" />
                  <circle cx="42" cy="42" r="34" fill="none" stroke={COLOR[tone(pillars[pillar.key])]} stroke-width="9" stroke-linecap="round" stroke-dasharray={ring(pillars[pillar.key], 34)} class="fs__arc" /></svg>
                <span>{pillars[pillar.key] ?? '—'}</span>
              </span>
              <b>{pillar.label()}</b><small>{pillar.jp}</small>
            </button>
          {/each}
        </div>

        <div class="v2-cols2">
          <div class="v2-sec">
            <div class="v2-sh"><h2>{t('Duplicates')}</h2>{#if dupInside + dupShared}<div class="v2-sh__r"><span class="v2-tag is-dark">{t('{size} to free', { size: formatBytes(dupInside + dupShared) })}</span></div>{/if}</div>
            {#if !data.duplicates.measured_on_server}
              <p class="fs__muted">{t('No folder measured on its server yet: duplicates are found by the measure on the Windows server.')}</p>
            {:else if !dupFolders.length}
              <p class="fs__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('No duplicate found here.')}</p>
            {:else}
              <ul class="v2-feed">
                {#each dupFolders.slice(0, 8) as folder (folder.id)}
                  <li><a class="v2-fi" href={`/five-s/duplicates/${folder.id}`}>
                    <div class="v2-fi__t"><b>{folder.name}</b>
                      <small>{#if folder.inside}{t('{size} inside ({count} group(s))', { size: formatBytes(folder.inside), count: folder.groups })}{/if}{#if folder.inside && folder.shared}{' · '}{/if}{#if folder.shared}{t('at least {size} also in {count} other folder(s)', { size: formatBytes(folder.shared), count: folder.with })}{/if}</small></div>
                    <span class="v2-fi__r"><b>{formatBytes(folder.inside + folder.shared)}</b></span>
                  </a></li>
                {/each}
              </ul>
              {#if dupShared}<p class="fs__muted">{t('Between folders: an estimate from the biggest files of each folder (at least this much); inside a folder: every file of the same size, compared by fingerprint.')}</p>{/if}
            {/if}
          </div>
          <div class="v2-sec">
            <div class="v2-sh"><h2>{t('What to do first')}</h2></div>
            {#if topActions.length}
              <ol class="v2-feed fs__actions">
                {#each topActions as action, rank (action.pillar + action.text)}
                  <li class="v2-fi"><span class="fs__rank">{rank + 1}</span>
                    <div class="v2-fi__t"><b>{action.text}</b><small>{label(action.pillar)}</small></div>
                    <span class="v2-fi__r">{t('{count} folder(s)', { count: action.folders })}</span></li>
                {/each}
              </ol>
            {:else}
              <p class="fs__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('Nothing to do')}</p>
            {/if}
          </div>
        </div>

        <div class="v2-sec">
          <div class="v2-sh">
            <h2>{pillarSort === 'score' ? t('The folders, least kept first') : t('The folders, by « {pillar} »', { pillar: label(pillarSort) })}</h2>
            <div class="v2-sh__r"><label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Folder, server, zone…')} aria-label={t('Search a folder')} /></label></div>
          </div>
          <div class="v2-list">
            <div class="v2-row is-head fs__g">
              <span>{t('Folder')}</span><span>{t('Score')}</span>
              {#each PILLARS as pillar (pillar.key)}<span class="fs__c">{pillar.label()}</span>{/each}
              <span>{t('Next step')}</span>
            </div>
            {#each folders.slice(0, shown) as folder (folder.id)}
              <button type="button" class="v2-row fs__g fs__rowbtn" onclick={() => goto(`/five-s/explore/${folder.id}`)} oncontextmenu={openMenu(folder)}>
                <span class="v2-nm"><b>{folder.name}</b><small>{folder.server} · {folder.zone}{folder.size_bytes != null ? ` · ${formatBytes(folder.size_bytes)}` : ''}</small></span>
                <span><span class={`v2-tag is-${tone(folder.score) === 'none' ? 'mut' : tone(folder.score)}`}>{folder.score ?? '—'}</span></span>
                {#each PILLARS as pillar (pillar.key)}
                  <span class="fs__c"><span class="fs__dot" style={`--c:${COLOR[tone(folder.pillars[pillar.key])]}`} title={`${pillar.label()} : ${folder.pillars[pillar.key] ?? '—'}`}>{folder.pillars[pillar.key] ?? '—'}</span></span>
                {/each}
                <span class="fs__next">{folder.actions[0]?.text ?? t('Nothing to do')}{#if folder.actions.length > 1}<small> · {t('+{count} more', { count: folder.actions.length - 1 })}</small>{/if}</span>
              </button>
            {:else}
              <p class="v2-empty">{t('No folder matches your search.')}</p>
            {/each}
          </div>
          {#if folders.length > shown}
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm fs__more" onclick={() => (shown += 30)}>{t('Show {count} more', { count: Math.min(30, folders.length - shown) })}</button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>

<ContextMenu open={menu != null} title={menu?.folder.name ?? ''} subtitle={menu?.folder.path ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  .fs__main { gap: 26px; padding: 18px 22px 22px; }
  .fs__rings { display: flex; flex-wrap: wrap; align-items: center; gap: 26px; }
  .fs__big { position: relative; width: 140px; height: 140px; flex: none; }
  .fs__big svg, .fs__small svg { width: 100%; height: 100%; transform: rotate(-90deg); }
  .fs__big > span { position: absolute; inset: 0; display: flex; align-items: baseline; justify-content: center; gap: 3px; padding-top: 50px; }
  .fs__big b { font-size: 34px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__big small { color: var(--b2s-color-text-muted); }
  .fs__arc { transition: stroke-dasharray 0.8s var(--b2s-ease-out); }
  .fs__pillar { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px; border: 0; border-radius: 14px; background: transparent; font: inherit; color: inherit; cursor: pointer; }
  .fs__pillar:hover { background: #f6f7f9; }
  .fs__pillar.is-on { background: var(--b2s-accent-soft); }
  .fs__pillar b { font-size: 13px; }
  .fs__pillar small { color: var(--b2s-color-text-muted); font-size: 11px; font-style: italic; }
  .fs__small { position: relative; width: 84px; height: 84px; }
  .fs__small > span { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; }
  .fs__g { grid-template-columns: minmax(200px, 1.5fr) 60px repeat(5, 86px) minmax(160px, 1.5fr); min-width: 960px; }
  .fs__rowbtn { width: 100%; border: 0; border-bottom: 1px solid #f3f4f6; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .fs__c { text-align: center; }
  .fs__dot { display: inline-grid; place-items: center; min-width: 34px; padding: 1px 6px; border-radius: 8px; background: color-mix(in srgb, var(--c) 14%, white); color: var(--c);
    font-size: var(--b2s-fs-xs); font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__next { overflow: hidden; font-size: var(--b2s-fs-sm); text-overflow: ellipsis; white-space: nowrap; }
  .fs__next small { color: var(--b2s-color-text-muted); }
  .fs__rank { display: grid; place-items: center; width: 24px; height: 24px; flex: none; border-radius: 50%; background: #f0f2f5; font-size: var(--b2s-fs-xs); font-weight: 700; }
  .fs__actions { padding: 0; }
  .fs__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .fs__ok { display: flex; gap: 8px; align-items: center; margin: 0; color: var(--b2s-color-success-strong, #1a7f37); font-size: var(--b2s-fs-sm); }
  .fs__more { align-self: center; }
  .fs__off { display: flex; gap: 16px; align-items: flex-start; padding: 24px; border: 1px dashed var(--b2s-color-border-strong); border-radius: var(--b2s-radius-lg); }
  .fs__off > i { font-size: 28px; color: var(--b2s-color-info-strong); }
  .fs__off p { margin: 4px 0 12px; color: var(--b2s-color-text-muted); }
</style>
