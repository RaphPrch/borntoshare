<script lang="ts">
  import { t } from '$lib/i18n';
  import { apiGetList } from '$lib/api/client';
  import { attachTagToStorageRoot, detachTagFromStorageRoot } from '$lib/api/tags';
  import { reportUiError } from '$lib/errors';

  /**
   * Tags of a folder edited from the list itself: a « + » opens the tags of the platform, a tick adds or removes
   * one at once (administrators, and the guardians of the folder). The list updates without being reloaded.
   */
  type Tag = Record<string, any>;
  interface Props {
    rootId: number;
    tags: Tag[];
    onChange: (tags: Tag[]) => void;
  }

  let { rootId, tags, onChange }: Props = $props();
  let open = $state(false);
  let all = $state<Tag[]>([]);
  let query = $state('');
  let busy = $state<number | null>(null);

  const idOf = (tag: Tag) => Number(tag.id ?? tag.tag_id ?? 0);
  const nameOf = (tag: Tag) => String(tag.label ?? tag.name ?? tag.tag_name ?? '');
  let attached = $derived(new Set(tags.map(idOf)));
  let shown = $derived(all.filter((tag) => !query.trim() || nameOf(tag).toLowerCase().includes(query.trim().toLowerCase())).slice(0, 40));

  async function toggleOpen() {
    open = !open;
    if (open && !all.length) all = await apiGetList<Tag>(fetch, '/tags').catch(() => []);
  }
  async function flip(tag: Tag) {
    const id = idOf(tag);
    if (!id || busy) return;
    busy = id;
    try {
      if (attached.has(id)) {
        await detachTagFromStorageRoot(fetch, { tag_id: id, resource_id: rootId });
        onChange(tags.filter((item) => idOf(item) !== id));
      } else {
        await attachTagToStorageRoot(fetch, { tag_id: id, resource_id: rootId });
        onChange([...tags, tag]);
      }
    } catch (failure) {
      reportUiError(failure, t('Unable to change the tags of this folder.'), 'storage-roots.tags.inline');
    } finally {
      busy = null;
    }
  }
</script>

<span class="tq">
  <button type="button" class="tq__add" onclick={toggleOpen} aria-expanded={open} aria-label={t('Edit the tags')} title={t('Edit the tags')}><i class="bi bi-plus" aria-hidden="true"></i></button>
  {#if open}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="tq__pop" onkeydown={(event) => event.key === 'Escape' && (open = false)}>
      <input class="b2s-input" placeholder={t('Find a tag…')} bind:value={query} aria-label={t('Find a tag')} />
      <ul>
        {#each shown as tag (idOf(tag))}
          <li><label><input type="checkbox" checked={attached.has(idOf(tag))} disabled={busy !== null} onchange={() => flip(tag)} /> {nameOf(tag)}</label></li>
        {:else}
          <li class="tq__none">{all.length ? t('No tag matches.') : t('No tag yet: create them in Settings › Tags.')}</li>
        {/each}
      </ul>
      <button type="button" class="b2s-link-btn" onclick={() => (open = false)}>{t('Done')}</button>
    </div>
  {/if}
</span>

<style>
  .tq { position: relative; display: inline-flex; }
  .tq__add { width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; padding: 0; border: 1px dashed var(--b2s-color-border);
    border-radius: 6px; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .tq__add:hover { border-style: solid; color: var(--b2s-color-text); }
  .tq__pop { position: absolute; top: 24px; right: 0; z-index: 30; width: 240px; display: grid; gap: 8px; padding: 10px; border: 1px solid var(--b2s-color-border);
    border-radius: 12px; background: var(--b2s-color-surface, #fff); box-shadow: 0 8px 24px rgba(18, 59, 73, 0.14); }
  .tq__pop .b2s-input { height: 32px; }
  .tq__pop ul { display: grid; gap: 2px; max-height: 220px; overflow: auto; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .tq__pop label { display: flex; gap: 8px; align-items: center; padding: 3px 4px; border-radius: 6px; cursor: pointer; }
  .tq__pop label:hover { background: var(--b2s-color-surface-muted); }
  .tq__none { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
