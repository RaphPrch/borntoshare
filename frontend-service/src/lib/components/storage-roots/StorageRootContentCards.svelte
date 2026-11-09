<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatBytes, formatDateTime, timeAgo } from '$lib/utils/format';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import StorageRootGrowth from '$lib/components/storage-roots/StorageRootGrowth.svelte';

  /**
   * Content of a governed folder, as the worker read it during the last check of the folder: size, sub-folders
   * and files, then where the weight is (first-level sub-folders) and which file types. One hue, bars with
   * their value written: the figure never depends on the colour alone.
   */
  type Content = {
    bytes?: number | null;
    files?: number;
    folders?: number;
    truncated?: boolean;
    scanned_at?: string | null;
    top?: Array<{ name: string; bytes: number; files: number }>;
    types?: Array<{ ext: string; files: number }>;
    cold?: { '1y': { bytes: number; files: number }; '3y': { bytes: number; files: number } };
    cold_top?: Array<{ path: string; bytes: number; modified: string }>;
    junk?: { bytes: number; files: number; examples: string[] };
    last_modified?: string | null;
  };
  export let content: Content | null = null;
  export let onMeasure: (() => void) | null = null;
  export let rootId: number | null = null;

  const size = (bytes: number | null | undefined) => formatBytes(bytes);
  const count = (value: number | undefined) => (value == null ? '—' : value.toLocaleString('fr-FR'));
  // Empty sub-folders say nothing about where the weight is
  $: top = (content?.top ?? []).filter((row) => row.bytes > 0);
  $: maxTop = Math.max(1, ...top.map((row) => row.bytes));
  $: types = content?.types ?? [];
  $: maxType = Math.max(1, ...types.map((row) => row.files));
  $: floor = content?.truncated ? '≥ ' : '';
  // Age of the data: under a year, 1 to 3 years, over 3 years (share of the bytes)
  $: total = Number(content?.bytes ?? 0);
  $: c1 = Number(content?.cold?.['1y']?.bytes ?? 0);
  $: c3 = Number(content?.cold?.['3y']?.bytes ?? 0);
  $: ages = content?.cold && total > 0
    ? [
        { key: 'fresh', label: t('Changed this year'), bytes: total - c1 },
        { key: 'cold', label: t('1 to 3 years'), bytes: c1 - c3 },
        { key: 'frozen', label: t('Over 3 years'), bytes: c3 }
      ]
    : [];
  const pct = (value: number) => (total ? Math.round((value / total) * 100) : 0);
</script>

<section class="cc" aria-label={t('Content of the folder')}>
  <header>
    <h2>{t('Content')}</h2>
    <small>
      {#if content?.scanned_at}<span title={formatDateTime(content.scanned_at)}>{t('read {when} by the worker', { when: timeAgo(content.scanned_at) })}</span>{:else}{t('Not measured yet')}{/if}
      {#if onMeasure} · <button type="button" class="b2s-link-btn" on:click={onMeasure}>{t('Measure again')}</button>{/if}
    </small>
  </header>
  {#if content}
    <div class="cc__tiles">
      <div class="cc__tile"><i class="bi bi-hdd" aria-hidden="true"></i><span>{t('Size')}</span><b>{floor}<CountUp value={content.bytes} format={(n) => size(Math.round(n))} /></b></div>
      <div class="cc__tile"><i class="bi bi-folder2" aria-hidden="true"></i><span>{t('Sub-folders')}</span><b>{floor}<CountUp value={content.folders} /></b></div>
      <div class="cc__tile"><i class="bi bi-file-earmark" aria-hidden="true"></i><span>{t('Files')}</span><b>{floor}<CountUp value={content.files} /></b></div>
    </div>
    {#if content.truncated}<small class="cc__note">{t('Very large folder: the figures are a minimum (the first 300,000 entries).')}</small>{/if}
    <!-- Another folder or a new measure: the bars fill again -->
    {#key content}
    <div class="cc__charts">
      {#if top.length}
        <div class="cc__chart">
          <h3>{t('Where the weight is')}</h3>
          {#each top as row, rank (row.name)}
            <div class="cc__bar" title={`${row.name} · ${size(row.bytes)} · ${t('{count} file(s)', { count: row.files })}`}>
              <span class="cc__label">{row.name}</span>
              <span class="cc__track"><i class="b2s-grow" style="width:{Math.max(2, (row.bytes / maxTop) * 100)}%;--i:{rank}"></i></span>
              <span class="cc__value">{size(row.bytes)}</span>
            </div>
          {/each}
        </div>
      {/if}
      {#if types.length}
        <div class="cc__chart">
          <h3>{t('File types')}</h3>
          {#each types as row, rank (row.ext)}
            <div class="cc__bar">
              <span class="cc__label mono">{row.ext === '—' ? t('no extension') : `.${row.ext}`}</span>
              <span class="cc__track"><i class="b2s-grow" style="width:{Math.max(2, (row.files / maxType) * 100)}%;--i:{rank}"></i></span>
              <span class="cc__value">{count(row.files)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
    {/key}
    {#if ages.length}
      <div class="cc__age">
        <div class="cc__age-head">
          <h3>{t('Age of the data')}</h3>
          {#if content.last_modified}<small>{t('last change {when}', { when: timeAgo(content.last_modified) })}</small>{/if}
        </div>
        <div class="cc__stack" role="img" aria-label={ages.map((age) => `${age.label} : ${pct(age.bytes)} %`).join(', ')}>
          {#each ages as age, rank (age.key)}{#if age.bytes > 0}<i class={`b2s-grow is-${age.key}`} style={`flex:${age.bytes};--i:${rank}`}></i>{/if}{/each}
        </div>
        <ul class="cc__legend">
          {#each ages as age (age.key)}<li><span class={`cc__key is-${age.key}`}></span>{age.label} <b>{pct(age.bytes)} %</b> <small>{size(age.bytes)}</small></li>{/each}
        </ul>
        {#if content.cold_top?.length}
          <details class="cc__more">
            <summary>{t('Biggest files untouched for a year')}</summary>
            <ul>{#each content.cold_top as file (file.path)}<li><code title={file.path}>{file.path}</code><span>{size(file.bytes)} · {timeAgo(file.modified)}</span></li>{/each}</ul>
          </details>
        {/if}
      </div>
    {/if}
    {#if content.junk?.files}
      <div class="cc__junk">
        <i class="bi bi-trash3" aria-hidden="true"></i>
        <span><b>{t('{count} clutter file(s)', { count: content.junk.files })}</b> · {size(content.junk.bytes)}
          <small>{t('Thumbnail caches, Office lock files, temporary files, backups and copies')} — {content.junk.examples.slice(0, 3).join(', ')}</small></span>
      </div>
    {/if}
    <StorageRootGrowth {rootId} refreshKey={content.scanned_at} />
  {:else}
    <p class="cc__empty">{t('The size, the sub-folders and the files appear after the next check of the folder by the worker.')}</p>
  {/if}
</section>

<style>
  .cc { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .cc header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .cc h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .cc header small, .cc__note, .cc__empty { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .cc__empty { margin: 0; }
  .cc__tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .cc__tile { display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 10px; align-items: center; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .cc__tile i { grid-row: 1 / 3; display: grid; place-items: center; width: 34px; height: 34px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 16px; }
  .cc__tile span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .cc__tile b { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .cc__charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .cc__chart { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .cc__chart h3 { margin: 0 0 2px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .cc__bar { display: grid; grid-template-columns: minmax(70px, 34%) minmax(0, 1fr) 64px; gap: 8px; align-items: center; font-size: var(--b2s-fs-xs); }
  .cc__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cc__track { height: 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; }
  .cc__track i { display: block; height: 100%; border-radius: inherit; background: var(--b2s-color-info-strong); }
  .cc__value { text-align: right; font-variant-numeric: tabular-nums; color: var(--b2s-color-text-muted); }
  .mono { font-family: var(--b2s-font-mono); }
  .cc__age { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
  .cc__age-head { display: flex; align-items: baseline; justify-content: space-between; }
  .cc__age h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .cc__age-head small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  /* One hue, three steps: light = recent, dark = frozen (sequential); a 2px gap between segments */
  .cc__stack { display: flex; gap: 2px; height: 12px; border-radius: var(--b2s-radius-pill); overflow: hidden; background: var(--b2s-color-neutral-soft); }
  .cc__stack i { display: block; height: 100%; }
  .is-fresh { background: #9ec5fe; }
  .is-cold { background: #3b82f6; }
  .is-frozen { background: #1e3a8a; }
  .cc__legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .cc__legend li { display: flex; align-items: center; gap: 6px; }
  .cc__legend small { color: var(--b2s-color-text-muted); }
  .cc__key { width: 10px; height: 10px; border-radius: 3px; }
  .cc__more summary { cursor: pointer; color: var(--b2s-color-info-strong); font-size: var(--b2s-fs-xs); }
  .cc__more ul { display: flex; flex-direction: column; gap: 4px; margin: 6px 0 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .cc__more li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
  .cc__more code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); }
  .cc__more span { color: var(--b2s-color-text-muted); font-variant-numeric: tabular-nums; }
  .cc__junk { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft, #fff4e5); font-size: var(--b2s-fs-sm); }
  .cc__junk i { color: var(--b2s-color-warning-strong, #9a5b00); margin-top: 2px; }
  .cc__junk small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
