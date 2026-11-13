<script lang="ts">
  import { createBubbler, preventDefault } from 'svelte/legacy';

  const bubble = createBubbler();
  import { t } from '$lib/i18n';
  import { applySuggestion, folderQueryExamples, folderSuggestions, parseFolderQuery, removeFilter } from '$lib/components/storage-roots/folder-query';

  
  
  
  
  interface Props {
    /**
   * Express search of the folders: the active filters as chips (× removes one), and proposals for the word
   * being typed (« fin » -> tag:Finance, gardien:… ; « gardien: » -> the guardians). Before typing, examples.
   */
    query?: string;
    rows?: Array<Record<string, any>>;
    tags?: string[];
    /** Folders left by the filters */
    count?: number | null;
    onQueryChange?: (value: string) => void;
    /** Proposals over the content (under a search field in a header) instead of in the flow */
    floating?: boolean;
    /** The search field has the focus: the examples show while it is empty */
    focused?: boolean;
  }

  let {
    query = '',
    rows = [],
    tags = [],
    count = null,
    onQueryChange = () => {},
    floating = false,
    focused = false
  }: Props = $props();

  let showExamples = $state(false);
  let parsed = $derived(parseFolderQuery(query));
  let suggestions = $derived(/\s$/.test(query) ? [] : folderSuggestions(query, rows, tags));
  let list = $derived(suggestions.length ? suggestions : (showExamples || (focused && !query.trim())) ? folderQueryExamples() : []);
  function pick(insert: string) {
    onQueryChange(applySuggestion(query, insert));
    showExamples = false;
  }
</script>

<div class="xq" class:is-floating={floating}>
  {#if parsed.filters.length && !floating}
    <div class="xq__chips" aria-label={t('Active filters')}>
      {#each parsed.filters as item (item.raw)}
        <button type="button" class="xq__chip" class:is-neg={item.neg} title={t('Remove this filter')} onclick={() => onQueryChange(removeFilter(query, item.raw))}>
          {item.raw}<i class="bi bi-x" aria-hidden="true"></i>
        </button>
      {/each}
      {#if count !== null}<small>{t('{count} folder(s)', { count })}</small>{/if}
    </div>
  {/if}
  {#if list.length}
    <ul class="xq__list" role="listbox" aria-label={t('Suggestions')}>
      {#each list as item (item.insert)}
        <li role="option" aria-selected="false">
          <!-- mousedown: the search field keeps the focus -->
          <button type="button" onmousedown={preventDefault(bubble('mousedown'))} onclick={() => pick(item.insert)}>
            <i class={`bi ${item.icon}`} aria-hidden="true"></i><span>{item.label}</span><code>{item.hint}</code>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
  {#if !floating && !query.trim()}
    <button type="button" class="b2s-link-btn xq__help" aria-expanded={showExamples} onclick={() => (showExamples = !showExamples)}>
      <i class="bi bi-lightning" aria-hidden="true"></i>{showExamples ? t('Hide the express filters') : t('Express filters: by tag, guardian, state…')}
    </button>
  {/if}
</div>

<style>
  .xq { display: flex; flex-direction: column; gap: 6px; margin: -2px 0 8px; }
  .xq.is-floating { margin: 0; }
  .xq.is-floating .xq__list { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 30; }
  .xq__chips { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
  .xq__chips small { margin-left: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .xq__chip { display: inline-flex; align-items: center; gap: 2px; padding: 2px 4px 2px 8px; border: 1px solid var(--b2s-color-info-strong); border-radius: var(--b2s-radius-pill); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); cursor: pointer; }
  .xq__chip.is-neg { border-color: var(--b2s-color-border); background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); text-decoration: line-through; }
  .xq__list { margin: 0; padding: 4px; list-style: none; max-height: 300px; overflow: auto; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm, 0 4px 14px rgba(0, 0, 0, 0.08)); }
  .xq__list button { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px; align-items: center; width: 100%; padding: 5px 8px; border: 0; border-radius: var(--b2s-radius-sm, 6px); background: none; color: inherit; text-align: left; font-size: var(--b2s-fs-sm); cursor: pointer; }
  .xq__list button:hover, .xq__list button:focus-visible { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .xq__list span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .xq__list code { color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .xq__list i { color: var(--b2s-color-text-muted); }
  .xq__help { align-self: flex-start; display: inline-flex; gap: 6px; align-items: center; font-size: var(--b2s-fs-xs); }
</style>
