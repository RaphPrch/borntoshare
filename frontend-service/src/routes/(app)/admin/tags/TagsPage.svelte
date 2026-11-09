<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import { reportUiError } from '$lib/errors/report';
  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import ConfirmDeleteDialog from '$lib/components/ui/ConfirmDeleteDialog.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import { attachTagToStorageRoot, createTag, deleteTag, mergeTag, updateTag } from '$lib/api/tags';
  import { listStorageRootsContext } from '$lib/api/storage-roots';
  import { toast } from '$lib/stores/toast';
  import { familyShades, fold, nameClash } from '$lib/utils/tag-colors';

  /**
   * Tags: how much of the governed folders they cover, the tags by family (one hue per family, its tags are shades),
   * one row per tag with its usage, and the folders of the selected tag. Creating a tag can set it on folders at once.
   */
  type Folder = { id: number; name: string; path: string; server: string };
  type Tag = { id: number; name: string; color: string | null; family: string | null; usage: number; folders: Folder[] };
  type Overview = { tags: Tag[]; coverage: { total: number; tagged: number; untagged_open: number } };

  export let data: { overview: unknown };

  const NO_FAMILY = '';
  $: overview = (data.overview ?? {}) as Partial<Overview>;
  $: tags = (overview.tags ?? []).map((tag) => ({ ...tag, usage: Number(tag.usage ?? 0), family: String(tag.family ?? '').trim() }));
  $: coverage = overview.coverage ?? { total: 0, tagged: 0, untagged_open: 0 };
  $: families = [...new Set(tags.map((tag) => tag.family).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
  $: maxUsage = Math.max(1, ...tags.map((tag) => tag.usage));
  $: taggedPct = coverage.total ? Math.round((coverage.tagged / coverage.total) * 100) : 0;

  let query = '';
  let sortBy = 'usage';
  $: needle = fold(query);
  $: sections = [...families, NO_FAMILY]
    .map((family) => ({
      family,
      tags: tags
        .filter((tag) => tag.family === family && (!needle || fold(tag.name).includes(needle) || fold(family).includes(needle)))
        .sort((a, b) => (sortBy === 'usage' ? b.usage - a.usage : 0) || a.name.localeCompare(b.name, 'fr'))
    }))
    .filter((section) => section.tags.length);

  let selectedId: number | null = null;
  $: selected = tags.find((tag) => tag.id === selectedId) ?? sections[0]?.tags[0] ?? null;

  // ---- create / edit ---------------------------------------------------------------
  let formOpen = false;
  let editing: Tag | null = null;
  let name = '';
  let family = NO_FAMILY;
  let newFamily = '';
  let addingFamily = false;
  let color = '';
  let saving = false;
  let folders: Folder[] | null = null;
  let folderQuery = '';
  let picked = new Set<number>();

  $: effectiveFamily = addingFamily ? newFamily.trim() : family;
  $: shades = familyShades(effectiveFamily);
  $: if (formOpen && !shades.includes(color) && !(editing && color === editing.color)) color = shades[0];
  $: clash = nameClash(name, tags.filter((tag) => tag.id !== editing?.id).map((tag) => tag.name));
  $: canSave = !saving && Boolean(name.trim()) && clash?.kind !== 'same' && (!addingFamily || Boolean(newFamily.trim()));
  $: pickedFolders = (folders ?? []).filter((folder) => picked.has(folder.id));
  $: folderMatches = (folders ?? []).filter((folder) => !fold(folderQuery) || fold(`${folder.name} ${folder.path}`).includes(fold(folderQuery))).slice(0, 40);
  $: preview = { name: name.trim() || t('New tag'), color };

  async function openForm(tag: Tag | null) {
    editing = tag;
    name = tag?.name ?? '';
    family = tag?.family ?? (selected?.family || NO_FAMILY);
    addingFamily = false;
    newFamily = '';
    color = tag?.color ?? '';
    picked = new Set();
    folderQuery = '';
    formOpen = true;
    if (!tag && folders === null) {
      try {
        folders = ((await listStorageRootsContext(fetch)) as any[]).map((row) => ({
          id: Number(row.storage_root_id ?? row.id),
          name: String(row.storage_root_name ?? row.name ?? ''),
          path: String(row.root_path ?? ''),
          server: String(row.storage_endpoint_name ?? '')
        }));
      } catch {
        folders = [];
      }
    }
  }
  function togglePick(id: number) {
    if (picked.has(id)) picked.delete(id);
    else picked.add(id);
    picked = picked;
  }

  async function save() {
    if (!canSave) return;
    saving = true;
    const payload = { name: name.trim(), color, family: effectiveFamily || null };
    try {
      if (editing) {
        await updateTag(fetch, editing.id, payload);
        toast.success(t('Tag updated.'));
        selectedId = editing.id;
      } else {
        const created = await createTag(fetch, payload);
        const id = Number((created as any)?.id ?? 0);
        let attached = 0;
        for (const folder of pickedFolders) {
          try {
            await attachTagToStorageRoot(fetch, { tag_id: id, resource_id: folder.id });
            attached += 1;
          } catch (error) {
            reportUiError(error, t('The tag was not set on {name}.', { name: folder.name }), 'tag.attach');
          }
        }
        toast.success(attached ? t('Tag created and set on {count} folder(s).', { count: attached }) : t('Tag created.'));
        selectedId = id || null;
      }
      formOpen = false;
      await invalidateAll();
    } catch (error) {
      reportUiError(error, t('Unable to save tag.'), 'tag.save');
    } finally {
      saving = false;
    }
  }

  // ---- merge / delete -----------------------------------------------------------------
  let mergeOpen = false;
  let mergeTargetId = 0;
  let merging = false;
  $: mergeTarget = tags.find((tag) => tag.id === Number(mergeTargetId)) ?? null;
  async function merge() {
    if (!selected || !mergeTarget) return;
    merging = true;
    try {
      await mergeTag(fetch, selected.id, mergeTarget.id);
      toast.success(t('Tags merged.'));
      mergeOpen = false;
      selectedId = mergeTarget.id;
      await invalidateAll();
    } catch (error) {
      reportUiError(error, t('Unable to merge tags.'), 'tag.merge');
    } finally {
      merging = false;
    }
  }

  let deleteOpen = false;
  let deleting = false;
  async function remove() {
    if (!selected) return;
    deleting = true;
    try {
      await deleteTag(fetch, selected.id);
      toast.success(t('Tag deleted.'));
      deleteOpen = false;
      selectedId = null;
      await invalidateAll();
    } catch (error) {
      reportUiError(error, t('Unable to delete tag.'), 'tag.delete');
    } finally {
      deleting = false;
    }
  }
</script>

{#if !tags.length}
  <EmptyState
    page
    iconClass="bi bi-tags"
    title={t('No tags yet')}
    description={t('Tags classify folders, for example by department or sensitivity, to find and govern them more easily.')}
    ctaLabel={t('Create your first tag')}
    onCta={() => openForm(null)}
  />
{:else}
  <section class="tg">
    <header class="tg__top">
      <div>
        <h1>{t('Tags')}</h1>
        <p>{t('Classify the folders to find and govern them more easily.')}</p>
      </div>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={() => openForm(null)}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Create a tag')}</button>
    </header>

    <div class="b2s-stat-tiles tg__tiles">
      <div class="b2s-stat-tile">
        <span>{t('Folders classified')}</span>
        <b>{taggedPct} %</b>
        <span class="b2s-stat-bar" aria-hidden="true">
          {#each families as name (name)}<i style="flex:{tags.filter((tag) => tag.family === name).reduce((sum, tag) => sum + tag.usage, 0)}; background:{familyShades(name)[0]}"></i>{/each}
          <i style="flex:{Math.max(0, coverage.total - coverage.tagged)}; background:transparent"></i>
        </span>
        <small>{t('{tagged} of {total} governed folders carry a tag', { tagged: coverage.tagged, total: coverage.total })}</small>
      </div>
      <a class="b2s-stat-tile" class:is-warn={coverage.untagged_open > 0} href="/exposure">
        <span>{t('Open to everyone, without a tag')}</span>
        <b>{coverage.untagged_open}</b>
        <small>{t('Folders that Everyone or Users reach and that no tag classifies · exposure map')}</small>
      </a>
      <div class="b2s-stat-tile">
        <span>{t('Families')}</span>
        <b>{families.length}</b>
        <small>{t('One colour per family, its tags are shades of it')}</small>
      </div>
    </div>

    <div class="tg__layout">
      <div class="tg__main">
        <div class="tg__tools">
          <label class="tg__search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Search a tag or a family')} aria-label={t('Search a tag or a family')} /></label>
          <SegmentedFilter bind:value={sortBy} ariaLabel={t('Sort')} options={[{ key: 'usage', label: t('Most used') }, { key: 'name', label: t('Name') }]} />
        </div>
        {#each sections as section (section.family)}
          <section class="tg__family" aria-label={section.family || t('No family')}>
            <header>
              <span class="tg__swatch" style="background:{familyShades(section.family)[0]}"></span>
              <b>{section.family || t('No family')}</b>
              <small>{t('{count} tag(s) · {uses} use(s)', { count: section.tags.length, uses: section.tags.reduce((sum, tag) => sum + tag.usage, 0) })}</small>
            </header>
            {#each section.tags as tag (tag.id)}
              <button type="button" class="tg__row" class:on={selected?.id === tag.id} aria-pressed={selected?.id === tag.id} on:click={() => (selectedId = tag.id)}>
                <TagPill label={tag.name} color={tag.color} />
                <span class="tg__bar"><i style="width:{(tag.usage / maxUsage) * 100}%; background:{tag.color ?? 'var(--b2s-color-text-muted)'}"></i></span>
                <span class="tg__count">{tag.usage}</span>
              </button>
            {/each}
          </section>
        {:else}
          <EmptyStateInline message={t('No tag matches this search.')} />
        {/each}
      </div>

      {#if selected}
        <aside class="tg__side" aria-label={selected.name}>
          <TagPill label={selected.name} color={selected.color} />
          <dl>
            <div><dt>{t('Family')}</dt><dd>{selected.family || t('No family')}</dd></div>
            <div><dt>{t('Set on')}</dt><dd><b>{selected.usage}</b> {t('folder(s)')}{coverage.total ? ` · ${Math.round((selected.usage / coverage.total) * 100)} %` : ''}</dd></div>
          </dl>
          {#if selected.usage}
            <h2>{t('Folders')}</h2>
            <ul class="tg__folders">
              {#each selected.folders as folder (folder.id)}
                <li><a href={`/storage-roots?selected=${folder.id}`}>{folder.name}</a><small>{folder.server}</small></li>
              {/each}
            </ul>
            {#if selected.usage > selected.folders.length}<small class="tg__more">{t('+ {count} other(s)', { count: selected.usage - selected.folders.length })}</small>{/if}
          {:else}
            <p class="tg__unused"><i class="bi bi-info-circle" aria-hidden="true"></i>{t('This tag is set on no folder: merge it into another one, or delete it.')}</p>
          {/if}
          <div class="tg__actions">
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => openForm(selected)}><i class="bi bi-pencil" aria-hidden="true"></i>{t('Edit')}</button>
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={tags.length < 2} on:click={() => { mergeTargetId = 0; mergeOpen = true; }}><i class="bi bi-intersect" aria-hidden="true"></i>{t('Merge…')}</button>
            <button type="button" class="b2s-btn b2s-btn-danger-outline b2s-btn-sm" disabled={selected.usage > 0} title={selected.usage > 0 ? t('Merge it first: it is set on folders') : ''} on:click={() => (deleteOpen = true)}><i class="bi bi-trash" aria-hidden="true"></i>{t('Delete')}</button>
          </div>
        </aside>
      {/if}
    </div>
  </section>
{/if}

<AppModal open={formOpen} onClose={() => (formOpen = false)} size="xl" ariaLabelledby="tag-form-title">
  <form class="tf" on:submit|preventDefault={save}>
    <header class="tf__head">
      <h2 id="tag-form-title">{editing ? t('Edit tag') : t('Create a tag')}</h2>
      <p>{editing ? editing.name : t('Its family gives its colour; set it on folders right away.')}</p>
    </header>
    <div class="tf__grid">
      <div class="tf__fields">
        <label class="tf__field">
          <span>{t('Tag name')}</span>
          <!-- svelte-ignore a11y-autofocus -->
          <input class="b2s-input tf__name" bind:value={name} placeholder={t('e.g. Confidential')} autocomplete="off" autofocus />
          {#if clash?.kind === 'same'}<small class="tf__hint is-bad">{t('« {name} » already exists: use it rather than a second one.', { name: clash.name })}</small>
          {:else if clash}<small class="tf__hint is-warn">{t('Close to « {name} »: the same thing? One tag keeps the searches right.', { name: clash.name })}</small>{/if}
        </label>
        <div class="tf__field">
          <span>{t('Family')}</span>
          <div class="tf__families">
            {#each [...families, NO_FAMILY] as option (option)}
              <button type="button" class:on={!addingFamily && family === option} aria-pressed={!addingFamily && family === option} on:click={() => { addingFamily = false; family = option; }}>
                <i style="background:{familyShades(option)[0]}"></i>{option || t('No family')}
              </button>
            {/each}
            {#if addingFamily}
              <input class="b2s-input tf__newfam" bind:value={newFamily} placeholder={t('New family')} aria-label={t('New family')} />
            {:else}
              <button type="button" on:click={() => (addingFamily = true)}>+ {t('New family')}</button>
            {/if}
          </div>
        </div>
        <div class="tf__field">
          <span>{t('Shade')}</span>
          <div class="tf__shades">
            {#each shades as shade (shade)}
              <button type="button" style="background:{shade}" aria-label={shade} aria-pressed={color === shade} class:on={color === shade} on:click={() => (color = shade)}></button>
            {/each}
          </div>
        </div>
        {#if !editing}
          <div class="tf__field">
            <span>{t('Set it right away on…')}</span>
            <input class="b2s-input" type="search" bind:value={folderQuery} placeholder={t('Search folders')} aria-label={t('Search folders')} />
            <div class="tf__pick">
              {#if folders === null}
                <LoadingState skeleton="rows" rows={3}>{t('Loading…')}</LoadingState>
              {:else}
                {#each folderMatches as folder (folder.id)}
                  <label><input type="checkbox" checked={picked.has(folder.id)} on:change={() => togglePick(folder.id)} /><span>{folder.name}</span><small>{folder.server}</small></label>
                {:else}
                  <small class="tf__none">{t('No folder matches.')}</small>
                {/each}
              {/if}
            </div>
          </div>
        {/if}
      </div>
      <aside class="tf__preview" aria-label={t('Preview')}>
        <span class="tf__label">{t('Preview')}</span>
        <TagPill label={preview.name} color={preview.color} />
        {#if !editing}
          <span class="tf__label">{t('On the folders')}</span>
          {#each pickedFolders.slice(0, 3) as folder (folder.id)}
            <div class="tf__mock"><span>{folder.name}</span><TagPill label={preview.name} color={preview.color} /></div>
          {:else}
            <small class="tf__none">{t('Tick folders to see the tag set on them.')}</small>
          {/each}
        {/if}
        <span class="tf__label">{t('In its family')}</span>
        <div class="tf__fam">
          {#each tags.filter((tag) => tag.family === effectiveFamily && tag.id !== editing?.id) as tag (tag.id)}<TagPill label={tag.name} color={tag.color} />{/each}
          <TagPill label={preview.name} color={preview.color} />
        </div>
      </aside>
    </div>
    <footer class="tf__foot">
      <button type="button" class="b2s-btn b2s-btn-secondary" disabled={saving} on:click={() => (formOpen = false)}>{t('Cancel')}</button>
      <button type="submit" class="b2s-btn b2s-btn-primary" disabled={!canSave}>
        <i class="bi {saving ? 'bi-arrow-repeat' : 'bi-check2'}" aria-hidden="true"></i>
        {editing ? t('Save changes') : picked.size ? t('Create and set on {count} folder(s)', { count: picked.size }) : t('Create the tag')}
      </button>
    </footer>
  </form>
</AppModal>

<AppModal open={mergeOpen} onClose={() => (mergeOpen = false)} size="md" ariaLabelledby="tag-merge-title">
  {#if selected}
    <div class="tf">
      <header class="tf__head">
        <h2 id="tag-merge-title">{t('Merge {name} into…', { name: selected.name })}</h2>
        <p>{t('Its folders move to the tag kept, then it is deleted.')}</p>
      </header>
      <select class="b2s-input" bind:value={mergeTargetId} aria-label={t('Tag to keep')}>
        <option value={0}>{t('Choose a tag…')}</option>
        {#each tags.filter((tag) => tag.id !== selected?.id) as tag (tag.id)}<option value={tag.id}>{tag.name}{tag.family ? ` · ${tag.family}` : ''}</option>{/each}
      </select>
      {#if mergeTarget}<small class="tf__hint is-warn">{t('{count} folders move to {target}, then {source} is deleted. This cannot be undone.', { count: selected.usage, target: mergeTarget.name, source: selected.name })}</small>{/if}
      <footer class="tf__foot">
        <button type="button" class="b2s-btn b2s-btn-secondary" disabled={merging} on:click={() => (mergeOpen = false)}>{t('Cancel')}</button>
        <button type="button" class="b2s-btn b2s-btn-primary" disabled={!mergeTarget || merging} on:click={merge}><i class="bi bi-intersect" aria-hidden="true"></i>{t('Merge')}</button>
      </footer>
    </div>
  {/if}
</AppModal>

<ConfirmDeleteDialog
  open={deleteOpen}
  onClose={() => (deleteOpen = false)}
  onConfirm={remove}
  busy={deleting}
  title={t('Delete the tag {name}?', { name: selected?.name ?? '' })}
  impactItems={[t('Irreversible deletion of this tag.')]}
/>

<style>
  .tg { padding: var(--b2s-page-padding, 24px 28px); display: flex; flex-direction: column; gap: 16px; }
  .tg__top { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
  .tg__top h1 { margin: 0; font-size: var(--b2s-fs-overview-title, 38px); line-height: 1.05; font-weight: 600; letter-spacing: -0.03em; }
  .tg__top p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .tg__tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .tg__tiles .b2s-stat-tile { text-align: left; text-decoration: none; color: inherit; }
  .tg__tiles .b2s-stat-tile > span:first-child { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tg__tiles .b2s-stat-tile b { display: block; margin: 4px 0; font-size: 26px; font-weight: 700; }
  .tg__tiles .b2s-stat-tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tg__tiles .b2s-stat-tile.is-warn b { color: var(--b2s-color-warning-strong); }
  .tg__layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
  .tg__main { display: flex; flex-direction: column; gap: 18px; padding: 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .tg__tools { display: flex; align-items: center; gap: 10px; }
  .tg__search { flex: 1; display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-md); }
  .tg__search input { flex: 1; border: 0; outline: 0; background: none; font: inherit; }
  .tg__family { display: flex; flex-direction: column; gap: 4px; }
  .tg__family header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .tg__family header small { color: var(--b2s-color-text-muted); }
  .tg__swatch { width: 12px; height: 12px; border-radius: 4px; }
  .tg__row { display: grid; grid-template-columns: minmax(150px, 240px) minmax(0, 1fr) 56px; gap: 12px; align-items: center; width: 100%; padding: 7px 10px; border: 1px solid transparent; border-radius: var(--b2s-radius-md); background: none; text-align: left; cursor: pointer; }
  .tg__row > :global(.b2s-tag-pill) { justify-self: start; max-width: 100%; }
  .tg__side > :global(.b2s-tag-pill), .tf__preview > :global(.b2s-tag-pill) { align-self: flex-start; }
  .tg__row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .tg__row.on { border-color: var(--b2s-color-text); }
  .tg__bar { height: 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; }
  .tg__bar i { display: block; height: 100%; min-width: 2px; border-radius: inherit; }
  .tg__count { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
  .tg__side { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 12px; padding: 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .tg__side dl { display: grid; gap: 8px; margin: 0; }
  .tg__side dt { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .tg__side dd { margin: 0; }
  .tg__side h2 { margin: 0; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .tg__folders { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .tg__folders li { display: flex; justify-content: space-between; gap: 8px; padding: 6px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-sm); font-size: var(--b2s-fs-sm); }
  .tg__folders small, .tg__more { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tg__unused { display: flex; gap: 8px; margin: 0; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-sm); }
  .tg__actions { display: flex; flex-wrap: wrap; gap: 6px; }
  .tf { display: flex; flex-direction: column; gap: 16px; padding: 4px; }
  .tf__head h2 { margin: 0; font-size: var(--b2s-fs-lg, 18px); font-weight: 600; }
  .tf__head p { margin: 2px 0 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tf__grid { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 20px; }
  .tf__fields { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .tf__field { display: flex; flex-direction: column; gap: 6px; }
  .tf__field > span { font-weight: 600; font-size: var(--b2s-fs-sm); }
  .tf__name { height: 48px; font-size: 18px; font-weight: 600; }
  .tf__hint { padding: 7px 10px; border-radius: var(--b2s-radius-sm); font-size: var(--b2s-fs-xs); }
  .tf__hint.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .tf__hint.is-warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .tf__families { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .tf__families button { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px 4px 8px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); font-size: var(--b2s-fs-sm); cursor: pointer; }
  .tf__families button i { width: 10px; height: 10px; border-radius: 3px; }
  .tf__families button.on { border-color: var(--b2s-color-text); box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
  .tf__newfam { width: 200px; }
  .tf__shades { display: flex; gap: 8px; }
  .tf__shades button { width: 30px; height: 30px; border: 2px solid var(--b2s-color-surface); border-radius: var(--b2s-radius-pill); box-shadow: 0 0 0 1px var(--b2s-color-border); cursor: pointer; }
  .tf__shades button.on { box-shadow: 0 0 0 2px var(--b2s-color-text); }
  .tf__pick { display: flex; flex-direction: column; gap: 2px; max-height: 200px; overflow: auto; padding: 6px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .tf__pick label { display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: var(--b2s-radius-sm); font-size: var(--b2s-fs-sm); cursor: pointer; }
  .tf__pick label:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .tf__pick small { margin-left: auto; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tf__none { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); padding: 4px; }
  .tf__preview { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 16px; border: 1.5px dashed var(--b2s-color-border); border-radius: var(--b2s-radius-lg); }
  .tf__label { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .tf__mock { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; padding: 6px 10px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-sm); }
  .tf__fam { display: flex; flex-wrap: wrap; gap: 6px; }
  .tf__foot { display: flex; justify-content: flex-end; gap: 8px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
</style>
