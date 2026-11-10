<script lang="ts">
  import { fivesEnabled } from '$lib/utils/features';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { apiGetData } from '$lib/api/client';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import FivesTabs from '$lib/components/fives/FivesTabs.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import { formatBytes } from '$lib/utils/format';

  /**
   * 5S of the file shares: the lean method applied to the governed folders. Each folder gets a score per pillar
   * from what BornToShare already measures, and the actions that would raise it. Worst folders first.
   */
  type Pillar = 'sort' | 'order' | 'shine' | 'standard' | 'sustain';
  type Folder = { id: number; name: string; path: string; server: string; zone: string; size_bytes: number | null; score: number | null;
    pillars: Record<Pillar, number | null>; actions: Array<{ pillar: Pillar; text: string }> };
  type FiveS = { score: number | null; pillars: Record<Pillar, number | null>; folders_count: number; scope: string;
    top_actions: Array<{ pillar: Pillar; text: string; folders: number }>; folders: Folder[]; zones: Array<{ id: number; name: string }>;
    duplicates: { inside_bytes: number; between_bytes: number; folders_count: number; measured_on_server: number;
      folders: Array<{ id: number; name: string; inside: number; groups: number; shared: number; with: number }> } };

  const PILLARS: Array<{ key: Pillar; label: () => string; jp: string; hint: () => string; icon: string }> = [
    { key: 'sort', label: () => t('5S: Sort'), jp: 'Seiri', hint: () => t('Keep what is used: data untouched for years goes to the archive, duplicates go.'), icon: 'bi-funnel' },
    { key: 'order', label: () => t('5S: Set in order'), jp: 'Seiton', hint: () => t('Each folder has its owners and its place: guardians, a tag, a quota.'), icon: 'bi-grid-3x3-gap' },
    { key: 'shine', label: () => t('5S: Shine'), jp: 'Seiso', hint: () => t('Nothing that should not be there: passwords, keys, clutter files.'), icon: 'bi-stars' },
    { key: 'standard', label: () => t('5S: Standardize'), jp: 'Seiketsu', hint: () => t('The folder follows the rule: inheritance, no error, reachable.'), icon: 'bi-rulers' },
    { key: 'sustain', label: () => t('5S: Sustain'), jp: 'Shitsuke', hint: () => t('It is kept up: measured and scanned recently, requests and corrections handled.'), icon: 'bi-arrow-repeat' }
  ];
  const label = (key: Pillar) => PILLARS.find((p) => p.key === key)?.label() ?? key;
  const tone = (score: number | null | undefined) => (score == null ? 'none' : score >= 80 ? 'ok' : score >= 60 ? 'warn' : 'bad');
  const verdict = (score: number | null | undefined) =>
    score == null ? t('Not enough data') : score >= 80 ? t('Well kept') : score >= 60 ? t('To improve') : t('To take in hand');

  let data: FiveS | null = null;
  let error = '';
  // The 5S is an optional module: switched off, the page says where to turn it on
  let disabled = false;
  let zoneId = 0;
  let pillarSort: Pillar | 'score' = 'score';
  let query = '';
  let shown = 30;

  // Not active (no license, switched off, or not installed): the explanation, no call to the module
  onMount(() => {
    if ($fivesEnabled) void load();
    else disabled = true;
  });
  async function load() {
    error = '';
    try {
      data = await apiGetData<FiveS>(fetch, '/modules/fives/five-s', zoneId ? { zone_id: zoneId } : undefined);
      shown = 30;
    } catch (failure) {
      const code = (failure as { code?: string; status?: number })?.code;
      if (code === 'FEATURE_DISABLED' || (failure as { status?: number })?.status === 403) disabled = true;
      else error = failure instanceof Error ? failure.message : t('Unable to load the 5S.');
    }
  }
  $: needle = query.trim().toLowerCase();
  $: folders = (data?.folders ?? [])
    .filter((f) => !needle || `${f.name} ${f.path} ${f.server} ${f.zone}`.toLowerCase().includes(needle))
    .slice()
    .sort((a, b) => {
      const va = pillarSort === 'score' ? a.score : a.pillars[pillarSort];
      const vb = pillarSort === 'score' ? b.score : b.pillars[pillarSort];
      return (va ?? 101) - (vb ?? 101);
    });
  // Ring of the overall score
  const R = 52;
  const C = 2 * Math.PI * R;
</script>

<section class="b2s-page b2s-page--admin fs">
  <FivesTabs />
  <header class="fs__head">
    <div>
      <h1>{t('5S of the shares')}</h1>
      <p>{t('Sort, set in order, shine, standardize, sustain: how well the folders are kept, and what to do first.')}</p>
    </div>
    {#if data?.zones?.length}
      <select class="b2s-input fs__zone" bind:value={zoneId} on:change={load} aria-label={t('Zone')}>
        <option value={0}>{t('All the zones')}</option>
        {#each data.zones as zone (zone.id)}<option value={zone.id}>{zone.name}</option>{/each}
      </select>
    {/if}
  </header>

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
    <EmptyStateInline message={t('No folder to score yet.')} />
  {:else}
    <div class="fs__top">
      <div class="fs__ring" data-tone={tone(data.score)}>
        <svg viewBox="0 0 120 120" role="img" aria-label={t('5S score: {score} out of 100', { score: data.score ?? '—' })}>
          <circle cx="60" cy="60" r={R} class="fs__track" />
          <circle cx="60" cy="60" r={R} class="fs__arc" stroke-dasharray={C} stroke-dashoffset={C * (1 - (data.score ?? 0) / 100)} />
        </svg>
        <div class="fs__ring-value"><b><CountUp value={data.score} /></b><small>/ 100</small></div>
        <span class="fs__verdict">{verdict(data.score)}</span>
        <small class="fs__scope">{data.scope} · {t('{count} folder(s)', { count: data.folders_count })}</small>
      </div>
      <div class="fs__pillars">
        {#each PILLARS as pillar, rank (pillar.key)}
          <button type="button" class="fs__pillar" class:is-on={pillarSort === pillar.key} data-tone={tone(data.pillars[pillar.key])}
            on:click={() => (pillarSort = pillarSort === pillar.key ? 'score' : pillar.key)} aria-pressed={pillarSort === pillar.key}
            title={t('Sort the folders by this pillar')}>
            <span class="fs__p-head"><i class={`bi ${pillar.icon}`} aria-hidden="true"></i><b>{pillar.label()}</b><small>{pillar.jp}</small></span>
            <span class="fs__p-score">{#if data.pillars[pillar.key] == null}—{:else}<CountUp value={data.pillars[pillar.key]} />{/if}</span>
            <span class="fs__p-bar"><i class="b2s-grow" style={`width:${data.pillars[pillar.key] ?? 0}%;--i:${rank}`}></i></span>
            <small class="fs__p-hint">{pillar.hint()}</small>
          </button>
        {/each}
      </div>
    </div>

    <section class="fs__card" aria-label={t('Duplicates')}>
      <header>
        <h2><i class="bi bi-files" aria-hidden="true"></i> {t('Duplicates')}</h2>
        <small>{t('Probable copies (same size and fingerprint), found when the folders are measured on their server')}</small>
      </header>
      {#if !data.duplicates.measured_on_server}
        <p class="fs__muted">{t('No folder measured on its server yet: duplicates are found by the measure on the Windows server.')}</p>
      {:else if !data.duplicates.folders_count}
        <p class="fs__ok"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('No duplicate found in the {count} folder(s) measured on their server.', { count: data.duplicates.measured_on_server })}</p>
      {:else}
        <div class="fs__dup-kpis">
          <div><b><CountUp value={data.duplicates.inside_bytes + data.duplicates.between_bytes} format={(n) => formatBytes(Math.round(n))} /></b><span>{t('to free')}</span></div>
          <div><b>{formatBytes(data.duplicates.inside_bytes)}</b><span>{t('inside the folders')}</span></div>
          <div><b>{formatBytes(data.duplicates.between_bytes)}</b><span>{t('between folders')}</span></div>
          <div><b>{data.duplicates.folders_count}</b><span>{t('folder(s) concerned')}</span></div>
        </div>
        <ul class="fs__dups">
          {#each data.duplicates.folders as folder (folder.id)}
            <li>
              <a href={`/storage-roots?selected=${folder.id}`}><b>{folder.name}</b></a>
              <span>{#if folder.inside}{t('{size} inside ({count} group(s))', { size: formatBytes(folder.inside), count: folder.groups })}{/if}{#if folder.inside && folder.shared}{' · '}{/if}{#if folder.shared}{t('{size} also in {count} other folder(s)', { size: formatBytes(folder.shared), count: folder.with })}{/if}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {#if data.top_actions.length}
      <section class="fs__card" aria-label={t('What to do first')}>
        <header><h2>{t('What to do first')}</h2><small>{t('The actions that would raise the score of the most folders')}</small></header>
        <ol class="fs__actions">
          {#each data.top_actions as action, rank (action.pillar + action.text)}
            <li>
              <span class="fs__rank">{rank + 1}</span>
              <span class="fs__chip">{label(action.pillar)}</span>
              <span class="fs__a-text">{action.text}</span>
              <b>{t('{count} folder(s)', { count: action.folders })}</b>
            </li>
          {/each}
        </ol>
      </section>
    {/if}

    <section class="fs__card" aria-label={t('Folders')}>
      <header>
        <h2>{pillarSort === 'score' ? t('The folders, least kept first') : t('The folders, by « {pillar} »', { pillar: label(pillarSort) })}</h2>
        <input class="b2s-input fs__search" type="search" bind:value={query} placeholder={t('Folder, server, zone…')} aria-label={t('Search a folder')} />
      </header>
      <div class="fs__table">
        <div class="fs__row is-head">
          <span>{t('Folder')}</span>
          <span>{t('Score')}</span>
          {#each PILLARS as pillar (pillar.key)}<span class="fs__c">{pillar.label()}</span>{/each}
          <span>{t('Next step')}</span>
        </div>
        {#each folders.slice(0, shown) as folder (folder.id)}
          <button type="button" class="fs__row" on:click={() => goto(`/storage-roots?selected=${folder.id}`)}>
            <span class="fs__name"><b>{folder.name}</b><small>{folder.server} · {folder.zone}{folder.size_bytes != null ? ` · ${formatBytes(folder.size_bytes)}` : ''}</small></span>
            <span><span class="fs__score" data-tone={tone(folder.score)}>{folder.score ?? '—'}</span></span>
            {#each PILLARS as pillar (pillar.key)}
              <span class="fs__c"><span class="fs__dot" data-tone={tone(folder.pillars[pillar.key])} title={`${pillar.label()} : ${folder.pillars[pillar.key] ?? '—'}`}>{folder.pillars[pillar.key] ?? '—'}</span></span>
            {/each}
            <span class="fs__next">{folder.actions[0]?.text ?? t('Nothing to do')}{#if folder.actions.length > 1}<small> · {t('+{count} more', { count: folder.actions.length - 1 })}</small>{/if}</span>
          </button>
        {:else}
          <p class="fs__empty">{t('No folder matches your search.')}</p>
        {/each}
      </div>
      {#if folders.length > shown}
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm fs__more" on:click={() => (shown += 30)}>{t('Show {count} more', { count: Math.min(30, folders.length - shown) })}</button>
      {/if}
    </section>
  {/if}
</section>

<style>
  .fs { display: flex; flex-direction: column; gap: 20px; padding: var(--b2s-page-padding, 24px 28px); }
  .fs__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .fs__head h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 650; }
  .fs__head p { margin: 4px 0 0; color: var(--b2s-color-text-muted); }
  .fs__zone { width: 220px; }
  .fs [data-tone='ok'] { --fs-tone: var(--b2s-color-success-strong, #1a7f37); --fs-soft: var(--b2s-color-success-soft, #eaf7ee); }
  .fs [data-tone='warn'] { --fs-tone: var(--b2s-color-warning-strong, #9a5b00); --fs-soft: var(--b2s-color-warning-soft, #fff4e5); }
  .fs [data-tone='bad'] { --fs-tone: var(--b2s-color-danger-strong, #b42318); --fs-soft: var(--b2s-color-danger-soft, #fdecea); }
  .fs [data-tone='none'] { --fs-tone: var(--b2s-color-text-muted); --fs-soft: var(--b2s-color-neutral-soft); }
  .fs__top { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; }
  .fs__ring { position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .fs__ring svg { width: 150px; height: 150px; transform: rotate(-90deg); }
  .fs__track { fill: none; stroke: var(--b2s-color-neutral-soft); stroke-width: 10; }
  .fs__arc { fill: none; stroke: var(--fs-tone); stroke-width: 10; stroke-linecap: round; transition: stroke-dashoffset 0.8s var(--b2s-ease-out); }
  .fs__ring-value { position: absolute; top: 70px; display: flex; align-items: baseline; gap: 4px; }
  .fs__ring-value b { font-size: 40px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__ring-value small { color: var(--b2s-color-text-muted); }
  .fs__verdict { padding: 2px 12px; border-radius: var(--b2s-radius-pill); background: var(--fs-soft); color: var(--fs-tone); font-weight: 600; font-size: var(--b2s-fs-sm); }
  .fs__scope { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); text-align: center; }
  .fs__pillars { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
  .fs__pillar { display: flex; flex-direction: column; gap: 8px; padding: 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; transition: box-shadow var(--b2s-motion-base) var(--b2s-ease-out), transform var(--b2s-motion-base) var(--b2s-ease-out), border-color var(--b2s-motion-fast); }
  .fs__pillar:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(14, 18, 24, 0.08); }
  .fs__pillar.is-on { border-color: var(--fs-tone); box-shadow: 0 0 0 2px var(--fs-soft); }
  .fs__p-head { display: flex; align-items: baseline; gap: 6px; }
  .fs__p-head i { color: var(--fs-tone); }
  .fs__p-head small { margin-left: auto; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-style: italic; }
  .fs__p-score { color: var(--fs-tone); font-size: 30px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__p-bar { height: 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; }
  .fs__p-bar i { display: block; height: 100%; border-radius: inherit; background: var(--fs-tone); }
  .fs__p-hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); line-height: 1.35; }
  .fs__card { display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .fs__card > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .fs__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .fs__card header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fs__actions { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; }
  .fs__actions li { display: grid; grid-template-columns: 26px 110px minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .fs__rank { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); font-weight: 700; }
  .fs__chip { justify-self: start; padding: 1px 10px; border-radius: var(--b2s-radius-pill); border: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-xs); }
  .fs__actions b { font-variant-numeric: tabular-nums; }
  .fs__search { width: 280px; }
  .fs__table { display: flex; flex-direction: column; }
  .fs__row { display: grid; grid-template-columns: minmax(0, 1.5fr) 60px repeat(5, 96px) minmax(0, 1.5fr); align-items: center; gap: 10px; padding: 9px 6px; border: 0; border-top: 1px solid var(--b2s-color-border); background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; border-radius: 8px; }
  .fs__row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .fs__row.is-head { cursor: default; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; border-top: 0; }
  .fs__row.is-head:hover { background: transparent; }
  .fs__c { text-align: center; }
  .fs__name { display: flex; flex-direction: column; min-width: 0; }
  .fs__name b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .fs__name small, .fs__next small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fs__score { display: inline-grid; place-items: center; min-width: 40px; padding: 3px 8px; border-radius: var(--b2s-radius-pill); background: var(--fs-soft); color: var(--fs-tone); font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__dot { display: inline-grid; place-items: center; min-width: 34px; padding: 1px 6px; border-radius: 8px; background: var(--fs-soft); color: var(--fs-tone); font-size: var(--b2s-fs-xs); font-weight: 600; font-variant-numeric: tabular-nums; }
  .fs__next { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-sm); }
  .fs__empty { margin: 12px 0; color: var(--b2s-color-text-muted); }
  .fs__off { display: flex; gap: 16px; align-items: flex-start; padding: 24px; border: 1px dashed var(--b2s-color-border-strong); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .fs__off > i { font-size: 28px; color: var(--b2s-color-info-strong); }
  .fs__off p { margin: 4px 0 12px; color: var(--b2s-color-text-muted); }
  .fs__muted { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .fs__ok { display: flex; gap: 8px; align-items: center; margin: 0; color: var(--b2s-color-success-strong, #1a7f37); font-size: var(--b2s-fs-sm); }
  .fs__card h2 i { color: var(--b2s-color-info-strong); }
  .fs__dup-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .fs__dup-kpis div { display: flex; flex-direction: column; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); }
  .fs__dup-kpis b { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .fs__dup-kpis span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .fs__dups { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .fs__dups li { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-top: 1px solid var(--b2s-color-border); }
  .fs__dups a { color: inherit; text-decoration: none; }
  .fs__dups span { color: var(--b2s-color-text-muted); }
  .fs__more { align-self: center; }
</style>
