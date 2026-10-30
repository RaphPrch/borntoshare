<script lang="ts">
  import { formatDateTime } from '$lib/utils/format';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import { normalizeText } from '$lib/utils/values';
  import { invalidateAll } from "$app/navigation";

  import ConfirmDeleteDialog from "$lib/components/ui/ConfirmDeleteDialog.svelte";
  import EntityActionButton from "$lib/components/entity/EntityActionButton.svelte";
  import TagPill from "$lib/components/tags/TagPill.svelte";
  import EmptyState from "$lib/components/ui/EmptyState.svelte";
  import { createTag, updateTag, deleteTag, mergeTag, type TagOverview } from "$lib/api/tags";
  import { showApiErrorToast } from "$lib/errors/api-toast";
  import { toast } from "$lib/stores/toast";
  import {
    dependencyCountDeleteMessage,
    dependencyDeleteMessage,
    isDependencyDeleteError
  } from "$lib/utils/delete-guard";

  export let data: {
    tags: Array<(TagOverview & { usage?: number } & { color?: string | null })>;
  };

  const getUsage = (tag: any) => (typeof tag?.usage === "number" ? tag.usage : 0);

  // Normalize core-service shape (id,name,color,usage) into UI shape (label,color_rgb)
  // so TagPill + modal edition always work.
  $: tagsNorm = (data.tags ?? []).map((tag: any) => ({
    ...tag,
    label: tag.label ?? tag.name ?? tag.code ?? t('Tag'),
    color_rgb: tag.color_rgb ?? tag.color ?? null
  }));

  let selectedId: number | null = null;
  $: selectedTag = tagsNorm.find((tag) => tag.id === selectedId) ?? null;
  let modalOpen = false;
  let modalMode: "create" | "edit" = "create";
  let showDeleteConfirm = false;
  let busy = false;
  let errorMsg: string | null = null;

  let form = {
    name: "",
    color_rgb: "",
    family: ""
  };

  let searchQuery = "";
  let sortBy: "name" | "usage" = "usage";

  const palette = [
    "#5b7cfa",
    "#38bdf8",
    "#22c55e",
    "#facc15",
    "#fb923c",
    "#f97316",
    "#fb7185",
    "#c084fc",
    "#a78bfa",
    "#64748b"
  ];

  const toSlug = (value: string) =>
    value
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-_]/g, "");

  const isValidHexColor = (value: string) => {
    const v = value.trim();
    if (!v) return true;
    return /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v);
  };

  const formatUpdatedAt = (raw: unknown) => {
    return formatDateTime(raw);
  };

  $: hasNameError = !form.name.trim();
  $: hasColorError = !isValidHexColor(form.color_rgb);
  $: canSubmit = !busy && !hasNameError && !hasColorError;

  const NO_FAMILY = "__none__";
  let familyFilter = "all";
  const familyOf = (tag: any): string => String(tag?.family ?? "").trim();
  $: families = [...new Set(tagsNorm.map(familyOf).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fr", { sensitivity: "base" }));
  // The filter of a family that no longer exists (last tag merged or renamed) falls back to all
  $: if (familyFilter !== "all" && familyFilter !== NO_FAMILY && !families.includes(familyFilter)) familyFilter = "all";
  $: familyChips = [
    { key: "all", label: t('All'), count: tagsNorm.length },
    ...families.map((family) => ({ key: family, label: family, count: tagsNorm.filter((tag) => familyOf(tag) === family).length })),
    ...(families.length ? [{ key: NO_FAMILY, label: t('No family'), count: tagsNorm.filter((tag) => !familyOf(tag)).length }] : [])
  ];

  let mergeOpen = false;
  let mergeTargetId = "";
  let merging = false;
  $: mergeCandidates = tagsNorm
    .filter((tag) => tag.id !== selectedId)
    .sort((a, b) => String(a.label).localeCompare(String(b.label), "fr", { sensitivity: "base" }));
  $: mergeTarget = tagsNorm.find((tag) => String(tag.id) === mergeTargetId) ?? null;

  function openMerge(): void {
    mergeTargetId = "";
    mergeOpen = true;
  }

  async function handleMerge(): Promise<void> {
    if (!selectedTag || !mergeTarget) return;
    merging = true;
    try {
      await mergeTag(fetch, selectedTag.id, Number(mergeTarget.id));
      toast.success(t('Tags merged.'));
      mergeOpen = false;
      selectedId = Number(mergeTarget.id);
      await invalidateAll();
    } catch (e) {
      showApiErrorToast(e, "Unable to merge tags.");
    } finally {
      merging = false;
    }
  }

  $: filteredTags = tagsNorm.filter((tag: any) => {
    if (familyFilter !== "all" && (familyFilter === NO_FAMILY ? familyOf(tag) : familyOf(tag) !== familyFilter)) return false;
    const q = normalizeText(searchQuery);
    if (!q) return true;
    const haystack = [tag?.label, tag?.name, tag?.code, tag?.family]
      .map((v) => normalizeText(v))
      .join(" ");
    return haystack.includes(q);
  });

  $: sortedTags = [...filteredTags].sort((a: any, b: any) => {
    const byName = String(a?.label ?? a?.name ?? "").localeCompare(String(b?.label ?? b?.name ?? ""), "fr", { sensitivity: "base" });
    return sortBy === "usage" ? getUsage(b) - getUsage(a) || byName : byName;
  });
  $: maxUsage = Math.max(1, ...tagsNorm.map(getUsage));
  $: totalUsage = tagsNorm.reduce((total, tag) => total + getUsage(tag), 0);

  // A tag used on more than half of what the top tag covers takes two columns
  const tileStyle = (tag: any, max: number): string =>
    `background:color-mix(in srgb, ${tag.color_rgb || "var(--b2s-color-text-faint)"} 24%, var(--b2s-color-surface));` +
    (getUsage(tag) > max * 0.5 && max > 1 ? "grid-column:span 2;" : "");

  function openEditTag(tag: any) {
    if (!tag) return;
    selectedId = Number(tag.id);
    modalMode = "edit";
    errorMsg = null;
    form = {
      name: tag.name ?? tag.label ?? "",
      color_rgb: tag.color_rgb ?? tag.color ?? "",
      family: tag.family ?? ""
    };
    modalOpen = true;
  }

  function openCreate() {
    modalMode = "create";
    errorMsg = null;
    form = { name: "", color_rgb: "", family: familyFilter === NO_FAMILY || familyFilter === "all" ? "" : familyFilter };
    modalOpen = true;
  }

  function openDelete() {
    if (!selectedTag) return;
    errorMsg = null;
    const usage = getUsage(selectedTag);
    if (usage > 0) {
      toast.error(dependencyCountDeleteMessage("tag", usage, "resource"));
      return;
    }
    showDeleteConfirm = true;
  }

  function closeDeleteConfirm() {
    showDeleteConfirm = false;
  }

  async function handleSubmit() {
    if (!canSubmit) return;

    busy = true;
    errorMsg = null;

    const name = form.name.trim();
    const label = name;
    const code = toSlug(name);
    const color_rgb = form.color_rgb.trim() || null;
    const color = color_rgb;
    const family = form.family.trim() || null;

    try {
      if (!name) {
        throw new Error("Tag name is required.");
      }

      if (!isValidHexColor(form.color_rgb)) {
        throw new Error("Color must be a valid hex code (#RGB or #RRGGBB).");
      }

      if (modalMode === "create") {
        await createTag(fetch, { name, label, code, color_rgb, color, family });
        toast.success(t('Tag created.'));
      } else if (modalMode === "edit" && selectedTag) {
        await updateTag(fetch, selectedTag.id, { name, label, code, color_rgb, color, family });
        toast.success(t('Tag updated.'));
      }

      modalOpen = false;
      await invalidateAll();
    } catch (e) {
      errorMsg = e?.message ?? t('Operation failed.');
      showApiErrorToast(e, "Unable to save tag.");
    } finally {
      busy = false;
    }
  }

  async function handleDelete() {
    if (!selectedTag) return;

    if (getUsage(selectedTag) > 0) {
      toast.error(dependencyCountDeleteMessage("tag", getUsage(selectedTag), "resource"));
      showDeleteConfirm = false;
      return;
    }

    busy = true;
    errorMsg = null;

    try {
      await deleteTag(fetch, selectedTag.id);
      toast.success(t('Tag deleted.'));
      showDeleteConfirm = false;
      selectedId = null;
      await invalidateAll();
    } catch (e) {
      const msg = e?.message ?? t('Delete failed.');
      errorMsg = msg;
      if (isDependencyDeleteError(e)) {
        const usage = getUsage(selectedTag);
        toast.error(usage > 0 ? dependencyCountDeleteMessage("tag", usage, "resource") : dependencyDeleteMessage("tag", "resources"));
        showDeleteConfirm = false;
      } else {
        showApiErrorToast(e, "Unable to delete tag.");
      }
    } finally {
      busy = false;
    }
  }
</script>

<section class="tg">
  <header class="sg-head">
    <div class="sg-title">
      <h1>{t('Tags')}</h1>
      <p>{t('{tags} tags, {count} uses on folders', { tags: tagsNorm.length, count: totalUsage })}</p>
    </div>
    <label class="sg-search" style="flex-basis:300px">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" aria-label={t('Search for a tag')} placeholder={t('Search by name or family')} bind:value={searchQuery} />
    </label>
    <div class="sg-seg" role="group" aria-label={t('Sort')}>
      <button type="button" class:on={sortBy === "usage"} aria-pressed={sortBy === "usage"} on:click={() => (sortBy = "usage")}>{t('Usage')}</button>
      <button type="button" class:on={sortBy === "name"} aria-pressed={sortBy === "name"} on:click={() => (sortBy = "name")}>{t('Name')}</button>
    </div>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={openCreate}>
      <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Create tag')}
    </button>
  </header>

  {#if families.length}
    <div class="sg-chips" role="group" aria-label={t('Family')}>
      {#each familyChips as chip (chip.key)}
        <button type="button" class:on={familyFilter === chip.key} aria-pressed={familyFilter === chip.key} on:click={() => (familyFilter = chip.key)}>{chip.label} · {chip.count}</button>
      {/each}
    </div>
  {/if}

  <div class="tg__body">
    <section class="tg__tiles" aria-label={t('Tags')}>
      {#each sortedTags as tag (tag.id)}
        <button
          type="button"
          class="tg__tile"
          class:sel={tag.id === selectedId}
          style={tileStyle(tag, maxUsage)}
          on:click={() => (selectedId = tag.id)}
          on:dblclick={() => openEditTag(tag)}
        >
          <strong>{tag.label}</strong>
          <span>{t('{count} folders', { count: getUsage(tag) })}</span>
        </button>
      {:else}
        <div class="tg__empty">
          <EmptyState
            iconClass="bi bi-tags"
            title={t('No tags found')}
            description={t('Create a tag or adjust your search.')}
            ctaLabel={t('Create tag')}
            onCta={openCreate}
          />
        </div>
      {/each}
    </section>

    <aside class="b2s-panel tg__side" aria-label={t('Details')}>
      {#if selectedTag}
        <div>
          <TagPill label={selectedTag.label} color={selectedTag.color_rgb ?? null} />
          <h2>{selectedTag.label}</h2>
          {#if selectedTag.code}<code>{selectedTag.code}</code>{/if}
        </div>
        <dl>
          <div class="wide"><dt>{t('Family')}</dt><dd>{familyOf(selectedTag) || t('No family')}</dd></div>
          <div><dt>{t('Usage')}</dt><dd>{t('{count} folders', { count: getUsage(selectedTag) })}</dd></div>
          <div><dt>{t('Updated')}</dt><dd>{formatUpdatedAt(selectedTag.updated_at ?? selectedTag.created_at)}</dd></div>
        </dl>
        <div class="tg__actions">
          <button type="button" class="b2s-btn b2s-btn-primary" on:click={() => openEditTag(selectedTag)}>{t('Edit tag')}</button>
          <button
            type="button"
            class="b2s-btn b2s-btn-danger-outline"
            disabled={getUsage(selectedTag) > 0}
            title={getUsage(selectedTag) > 0 ? dependencyCountDeleteMessage("tag", getUsage(selectedTag), "resource") : undefined}
            on:click={openDelete}
          >{t('Delete')}</button>
        </div>
        <button type="button" class="b2s-btn b2s-btn-secondary" disabled={mergeCandidates.length === 0} on:click={openMerge}>{t('Merge with…')}</button>
      {:else}
        <div class="sg-side-empty">
          <i class="bi bi-tags" aria-hidden="true"></i>
          <p>{t('Select a tag to see where it is used.')}</p>
        </div>
      {/if}
    </aside>
  </div>
</section>

<AppModal
  open={modalOpen}
  onClose={() => (modalOpen = false)}
  size="lg"
  title={modalMode === "create" ? t('Create tag') : t('Edit tag')}
  subtitle={t('Define and create a customizable tag for your resources.')}
  iconClass="bi bi-tag"
  contentClass="b2s-modal-content tag-modal__body"
>
      <section class="tag-modal__section">
          <label for="tag-name">{t('Tag name')}</label>
          <input
            id="tag-name"
            class="tag-input"
            placeholder={t('e.g. Sensitive')}
            bind:value={form.name}
          />
      </section>

      <section class="tag-modal__section">
          <label for="tag-family">{t('Family')} <small>{t('(optional)')}</small></label>
          <input
            id="tag-family"
            class="tag-input"
            list="tag-family-options"
            maxlength="100"
            placeholder={t('e.g. Sensitivity')}
            bind:value={form.family}
          />
          <datalist id="tag-family-options">
            {#each families as family}<option value={family}></option>{/each}
          </datalist>
      </section>

      <section class="tag-modal__grid">
          <div class="tag-card">
            <div class="tag-card__title">{t('Tag color')}</div>
            <div class="tag-palette">
              {#each palette as color}
                <button
                  type="button"
                  class="tag-swatch"
                  class:active={form.color_rgb === color}
                  style={`background:${color}`}
                  on:click={() => (form.color_rgb = color)}
                  aria-label={t('Color {color}', { color })}
                ></button>
              {/each}
            </div>
            <div class="tag-custom">
              <span class="tag-custom__label">{t('Custom…')}</span>
              <input
                class="tag-input tag-input--compact"
                placeholder="#3fa9f5"
                bind:value={form.color_rgb}
              />
            </div>
          </div>
      </section>

      {#if errorMsg}
        <InlineAlert tone="error">{errorMsg}</InlineAlert>
      {/if}

  <svelte:fragment slot="footer-start">
    {#if modalMode === "edit" && selectedTag}
      <EntityActionButton
        variant="danger-outline"
        icon="bi-trash"
        label={t('Delete tag')}
        disabled={getUsage(selectedTag) > 0}
        title={getUsage(selectedTag) > 0 ? dependencyCountDeleteMessage("tag", getUsage(selectedTag), "resource") : undefined}
        onClick={() => {
          modalOpen = false;
          openDelete();
        }}
      />
    {/if}
  </svelte:fragment>
  <svelte:fragment slot="footer">
    <EntityActionButton variant="ghost" label={t('Cancel')} onClick={() => (modalOpen = false)} />
    <EntityActionButton
      variant="primary"
      busy={busy}
      label={modalMode === "create" ? t('Create') : t('Save changes')}
      onClick={handleSubmit}
    />
  </svelte:fragment>
</AppModal>

<AppModal
  open={mergeOpen}
  onClose={() => (mergeOpen = false)}
  title={t('Merge {name} with another tag', { name: selectedTag?.label ?? '' })}
  iconClass="bi bi-union"
>
  <section class="tag-modal__section">
    <label for="tag-merge-target">{t('Tag to keep')}</label>
    <select id="tag-merge-target" class="tag-input" bind:value={mergeTargetId}>
      <option value="">{t('Choose a tag…')}</option>
      {#each mergeCandidates as tag (tag.id)}<option value={String(tag.id)}>{tag.label}</option>{/each}
    </select>
  </section>
  {#if selectedTag && mergeTarget}
    <InlineAlert tone="warning">
      {t('{count} folders move to {target}, then {source} is deleted. This cannot be undone.', { count: getUsage(selectedTag), target: mergeTarget.label, source: selectedTag.label })}
    </InlineAlert>
  {/if}
  <svelte:fragment slot="footer">
    <EntityActionButton variant="ghost" label={t('Cancel')} onClick={() => (mergeOpen = false)} />
    <EntityActionButton variant="primary" busy={merging} disabled={!mergeTarget} label={t('Merge')} onClick={handleMerge} />
  </svelte:fragment>
</AppModal>

<ConfirmDeleteDialog
  open={showDeleteConfirm}
  onClose={closeDeleteConfirm}
  onConfirm={handleDelete}
  ariaLabelledby="tags-delete-modal-title"
  title={t('Delete tag')}
  description={selectedTag?.label ?? selectedTag?.name ?? null}
  impactTitle={t('Consequences')}
  impactItems={[
    t('Irreversible deletion of this tag.'),
    t('Associated governance references must be recreated if needed.')
  ]}
  deleteLabel={t('Delete')}
  deleteBusyLabel={t('Deleting…')}
  busy={busy}
  requireTextConfirm={true}
  requiredText=DELETE
  textConfirmLabel={t('Type')}
  textConfirmPlaceholder=DELETE
/>

<style>
  :global(.b2s-app-root main) {
    padding: 0 !important;
  }

  .tg { display: flex; flex-direction: column; gap: 18px; padding: var(--b2s-page-padding); }
  .tg__body { display: flex; align-items: flex-start; gap: 18px; }
  .tg__tiles { flex: 1; min-width: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); grid-auto-flow: dense; gap: 10px; }
  .tg__tile { min-height: 84px; padding: 12px 14px; display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; gap: 10px; border: 1px solid transparent; border-radius: 14px; color: var(--b2s-color-text); font: inherit; text-align: left; cursor: pointer; transition: transform .12s; }
  .tg__tile:hover { transform: translateY(-2px); }
  .tg__tile.sel { outline: 2px solid var(--b2s-color-text); outline-offset: 2px; }
  .tg__tile strong { font-weight: 600; overflow-wrap: anywhere; }
  .tg__tile span { font-size: 13px; }
  .tg__empty { grid-column: 1 / -1; }
  .tg__side { flex: 0 0 340px; position: sticky; top: 16px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .tg__side h2 { margin: 10px 0 4px; font-size: 25px; font-weight: 600; letter-spacing: -.02em; overflow-wrap: anywhere; }
  .tg__side code { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); }
  .tg__side dl { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 10px; }
  .tg__side dl .wide { grid-column: 1 / -1; }
  .tg__side dt { font-size: 12px; font-weight: 400; color: var(--b2s-color-text-muted); }
  .tg__side dd { margin: 0; font-weight: 500; }
  .tg__actions { display: flex; gap: 8px; }
  .tg__actions .b2s-btn-primary { flex: 1; }

  .tag-modal__section {
    padding: 0;
    display: grid;
    gap: 8px;
  }

  .tag-modal__section label {
    font-weight: 700;
    color: #0b1530;
    font-size: var(--b2s-fs-sm);
  }

  .tag-input {
    height: 44px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 0 14px;
    font-weight: 700;
    outline: none;
  }

  .tag-input:focus {
    border-color: rgba(37, 99, 235, 0.55);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
  }

  .tag-modal__grid {
    padding: 0;
  }

  .tag-card {
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: var(--b2s-radius-lg);
    padding: 14px;
    background: linear-gradient(180deg, #ffffff 0%, var(--b2s-color-surface-soft) 100%);
  }

  .tag-card__title {
    font-weight: 700;
    color: #0b1530;
    margin-bottom: 10px;
  }

  .tag-palette {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  .tag-swatch {
    width: 26px;
    height: 26px;
    border-radius: var(--b2s-radius-pill);
    border: 2px solid rgba(255, 255, 255, 0.95);
    box-shadow: 0 8px 16px rgba(15, 23, 42, 0.10);
  }

  .tag-swatch.active {
    outline: 2px solid #0b1530;
    outline-offset: 2px;
  }

  .tag-custom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 12px;
  }

  .tag-custom__label {
    color: var(--b2s-color-text-muted);
    font-weight: 700;
    font-size: var(--b2s-fs-sm);
  }

  .tag-input--compact {
    height: 38px;
  }

</style>
