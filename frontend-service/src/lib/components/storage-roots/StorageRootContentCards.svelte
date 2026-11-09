<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatBytes, formatDateTime, timeAgo } from '$lib/utils/format';

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
  };
  export let content: Content | null = null;
  export let onMeasure: (() => void) | null = null;

  const size = (bytes: number | null | undefined) => formatBytes(bytes);
  const count = (value: number | undefined) => (value == null ? '—' : value.toLocaleString('fr-FR'));
  $: top = content?.top ?? [];
  $: maxTop = Math.max(1, ...top.map((row) => row.bytes));
  $: types = content?.types ?? [];
  $: maxType = Math.max(1, ...types.map((row) => row.files));
  $: floor = content?.truncated ? '≥ ' : '';
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
      <div class="cc__tile"><i class="bi bi-hdd" aria-hidden="true"></i><span>{t('Size')}</span><b>{floor}{size(content.bytes)}</b></div>
      <div class="cc__tile"><i class="bi bi-folder2" aria-hidden="true"></i><span>{t('Sub-folders')}</span><b>{floor}{count(content.folders)}</b></div>
      <div class="cc__tile"><i class="bi bi-file-earmark" aria-hidden="true"></i><span>{t('Files')}</span><b>{floor}{count(content.files)}</b></div>
    </div>
    {#if content.truncated}<small class="cc__note">{t('Very large folder: the figures are a minimum (the first 300,000 entries).')}</small>{/if}
    <div class="cc__charts">
      {#if top.length}
        <div class="cc__chart">
          <h3>{t('Where the weight is')}</h3>
          {#each top as row (row.name)}
            <div class="cc__bar" title={`${row.name} · ${size(row.bytes)} · ${t('{count} file(s)', { count: row.files })}`}>
              <span class="cc__label">{row.name}</span>
              <span class="cc__track"><i style="width:{Math.max(2, (row.bytes / maxTop) * 100)}%"></i></span>
              <span class="cc__value">{size(row.bytes)}</span>
            </div>
          {/each}
        </div>
      {/if}
      {#if types.length}
        <div class="cc__chart">
          <h3>{t('File types')}</h3>
          {#each types as row (row.ext)}
            <div class="cc__bar">
              <span class="cc__label mono">{row.ext === '—' ? t('no extension') : `.${row.ext}`}</span>
              <span class="cc__track"><i style="width:{Math.max(2, (row.files / maxType) * 100)}%"></i></span>
              <span class="cc__value">{count(row.files)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
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
</style>
