<script lang="ts">
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t, intlLocale } from '$lib/i18n';
  import { normalizeText } from '$lib/utils/values';
  import { invalidateAll } from "$app/navigation";

  import ConfirmDeleteDialog from "$lib/components/ui/ConfirmDeleteDialog.svelte";
  import EntityActionButton from "$lib/components/entity/EntityActionButton.svelte";
  import EntityActionGroup, { type EntityActionItem } from "$lib/components/entity/EntityActionGroup.svelte";
  import SearchField from "$lib/components/ui/SearchField.svelte";
  import TagPill from "$lib/components/tags/TagPill.svelte";
  import EmptyState from "$lib/components/ui/EmptyState.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import { createTag, updateTag, deleteTag, type TagOverview } from "$lib/api/tags";
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
    value_text: ""
  };

  let valueInput = "";
  let valueItems: string[] = [];

  let searchQuery = "";
  let sortBy: "name" | "usage" | "updated" = "name";
  let sortDir: "asc" | "desc" = "asc";

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

  const splitValues = (value: string | null | undefined) =>
    String(value ?? "")
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);

  const uniqueValues = (values: string[]) => Array.from(new Set(values.map((v) => v.trim()).filter(Boolean)));

  const formatUpdatedAt = (raw: unknown) => {
    if (!raw) return "—";
    const d = new Date(String(raw));
    if (!Number.isFinite(d.getTime())) return "—";
    return d.toLocaleString(intlLocale(), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  $: hasNameError = !form.name.trim();
  $: hasColorError = !isValidHexColor(form.color_rgb);
  $: canSubmit = !busy && !hasNameError && !hasColorError;

  $: filteredTags = tagsNorm.filter((tag: any) => {
    const q = normalizeText(searchQuery);
    if (!q) return true;
    const haystack = [tag?.label, tag?.name, tag?.code, tag?.value_text]
      .map((v) => normalizeText(v))
      .join(" ");
    return haystack.includes(q);
  });

  $: sortedTags = [...filteredTags].sort((a: any, b: any) => {
    const dir = sortDir === "asc" ? 1 : -1;
    if (sortBy === "usage") return (getUsage(a) - getUsage(b)) * dir;
    if (sortBy === "updated") {
      const ta = new Date(String(a?.updated_at ?? a?.created_at ?? 0)).getTime() || 0;
      const tb = new Date(String(b?.updated_at ?? b?.created_at ?? 0)).getTime() || 0;
      return (ta - tb) * dir;
    }
    return String(a?.label ?? a?.name ?? "").localeCompare(String(b?.label ?? b?.name ?? ""), "fr", { sensitivity: "base" }) * dir;
  });

  $: tagActions = [
    {
      key: "new",
      label: t('Create tag'),
      icon: "bi-plus-lg",
      variant: "primary",
      onClick: openCreate
    },
    {
      key: "edit",
      label: t('Edit tag'),
      icon: "bi-pencil-square",
      variant: "secondary",
      disabled: !selectedTag,
      onClick: openEdit
    },
    {
      key: "delete",
      label: t('Delete tag'),
      icon: "bi-trash",
      variant: "danger",
      disabled: !selectedTag || getUsage(selectedTag) > 0,
      title: !selectedTag
        ? t('Select a tag first')
        : getUsage(selectedTag) > 0
          ? dependencyCountDeleteMessage("tag", getUsage(selectedTag), "resource")
          : undefined,
      onClick: openDelete
    }
  ] satisfies EntityActionItem[];

  function openEditTag(tag: any) {
    if (!tag) return;
    selectedId = Number(tag.id);
    modalMode = "edit";
    errorMsg = null;
    form = {
      name: tag.name ?? tag.label ?? "",
      color_rgb: tag.color_rgb ?? tag.color ?? "",
      value_text: tag.value_text ?? ""
    };
    valueItems = splitValues(form.value_text);
    valueInput = "";
    modalOpen = true;
  }

  function addValueItem() {
    const v = valueInput.trim();
    if (!v) return;
    valueItems = uniqueValues([...valueItems, v]);
    form.value_text = valueItems.join(", ");
    valueInput = "";
  }

  function removeValueItem(value: string) {
    valueItems = valueItems.filter((v) => v !== value);
    form.value_text = valueItems.join(", ");
  }

  function openCreate() {
    modalMode = "create";
    errorMsg = null;
    form = { name: "", color_rgb: "", value_text: "" };
    valueItems = [];
    valueInput = "";
    modalOpen = true;
  }

  function openEdit() {
    if (!selectedTag) return;
    openEditTag(selectedTag);
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
    const value_text = uniqueValues(valueItems).join(", ").trim() || null;

    try {
      if (!name) {
        throw new Error("Tag name is required.");
      }

      if (!isValidHexColor(form.color_rgb)) {
        throw new Error("Color must be a valid hex code (#RGB or #RRGGBB).");
      }

      if (modalMode === "create") {
        await createTag(fetch, { name, label, code, color_rgb, color, value_text });
        toast.success(t('Tag created.'));
      } else if (modalMode === "edit" && selectedTag) {
        await updateTag(fetch, selectedTag.id, { name, label, code, color_rgb, color, value_text });
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

<section class="tags-page">
  <PageHeader title={t('Tags')} subtitle={t('All created tags are listed here.')}>
    <svelte:fragment slot="actions">
      <EntityActionGroup actions={tagActions} ariaLabel={t('Tag actions')} />
    </svelte:fragment>
  </PageHeader>

  <section class="tags-toolbar">
    <SearchField
      wrapperClass="tags-search"
      placeholder={t('Search by name, code, or value')}
      ariaLabel={t('Search for a tag')}
      bind:value={searchQuery}
    />
    <div class="tags-sort">
      <select bind:value={sortBy}>
        <option value="name">{t('Trier: Nom')}</option>
        <option value="usage">{t('Trier: Usage')}</option>
        <option value="updated">{t('Sort: Last updated')}</option>
      </select>
      <EntityActionButton
        variant="secondary"
        icon={sortDir === 'asc' ? 'bi-sort-down' : 'bi-sort-up'}
        label={sortDir === 'asc' ? t('Ascending') : t('Descending')}
        className="tags-sort-dir-btn"
        onClick={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}
      />
    </div>
  </section>

  <section class="tags-table">
    <div class="tags-table-head">
      <span>{t('Tag')}</span>
      <span>{t('Code')}</span>
      <span>{t('Usage')}</span>
      <span>{t('Updated')}</span>
    </div>

    <div class="tags-table-body">
      {#if Array.isArray(sortedTags) && sortedTags.length}
        {#each sortedTags as tag, index (tag.id)}
          <div
            class="tags-row"
            class:selected={tag.id === selectedId}
            role="button"
            tabindex="0"
            aria-pressed={tag.id === selectedId}
            on:click={() => (selectedId = tag.id)}
            on:dblclick={() => openEditTag(tag)}
            on:keydown={(e) => {
              if (e.key === "Enter") {
                selectedId = tag.id;
                return;
              }
              if (e.key === "ArrowDown") {
                e.preventDefault();
                const next = sortedTags[index + 1];
                if (next?.id) selectedId = next.id;
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                const prev = sortedTags[index - 1];
                if (prev?.id) selectedId = prev.id;
              }
            }}
          >
            <div class="tag-cell">
              <TagPill label={tag.label ?? tag.name ?? tag.code ?? t('Tag')} color={tag.color_rgb ?? null} />
            </div>
            <div class="tag-code">{tag.code ?? '—'}</div>
            <div class="tag-usage">{getUsage(tag)}</div>
            <div class="tag-updated">{formatUpdatedAt(tag.updated_at ?? tag.created_at)}</div>
          </div>
        {/each}
      {:else}
        <div class="tags-empty">
          <EmptyState
            iconClass="bi bi-tags"
            title={t('No tags found')}
            description={t('Create a tag or adjust your search.')}
            ctaLabel={t('Create tag')}
            onCta={openCreate}
          />
        </div>
      {/if}
    </div>
  </section>
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

      <section class="tag-card tag-card--wide">
          <div class="tag-card__title">{t('Value')}</div>
          <p class="tag-card__subtitle">{t('Create one or more predefined values for this tag')}</p>
          <div class="tag-value-row">
            <input
              class="tag-input"
              placeholder={t('e.g. Confidential')}
              bind:value={valueInput}
              on:keydown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addValueItem();
                }
              }}
            />
            <button
              class="tag-value-btn"
              type="button"
              on:click={addValueItem}
            >
              {t('Add value')}
            </button>
          </div>
          {#if valueItems.length > 0}
            <div class="tag-values-list">
              {#each valueItems as item (item)}
                <div class="tag-value-pill">
                  {item}
                  <button
                    type="button"
                    aria-label={t('Remove value')}
                    on:click={() => removeValueItem(item)}
                  >
                    ×
                  </button>
                </div>
              {/each}
            </div>
          {/if}
          <div class="tag-card__hint">{t('Suggested: Public, Sensitive, Private, Archived')}</div>
      </section>

      {#if errorMsg}
        <InlineAlert tone="error">{errorMsg}</InlineAlert>
      {/if}

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

<ConfirmDeleteDialog
  open={showDeleteConfirm}
  onClose={closeDeleteConfirm}
  onConfirm={handleDelete}
  ariaLabelledby="tags-delete-modal-title"
  title={t('Delete tag')}
  description={selectedTag?.label ?? selectedTag?.name ?? null}
  impactTitle={t('Consequences')}
  impactItems={[
    'Irreversible deletion of this tag.',
    'Associated governance references must be recreated if needed.'
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

  .tags-page {
    min-height: calc(100vh - 64px);
    padding: var(--b2s-page-padding);
    color: #0f172a;
  }

  :global(.tags-page .b2s-page-header__actions .b2s-action-group) {
    width: auto;
  }

  :global(.tags-page .b2s-tag-pill) {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    letter-spacing: 0.01em;
    background: color-mix(
      in srgb,
      var(--tag-color, #94a3b8) 22%,
      #ffffff
    );
    color: color-mix(
      in srgb,
      var(--tag-color, #475569) 78%,
      #0f172a
    );
    border: 1px solid color-mix(
      in srgb,
      var(--tag-color, #94a3b8) 45%,
      transparent
    );
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
  }

  .tags-table {
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: var(--b2s-radius-lg);
    box-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
    backdrop-filter: blur(12px);
  }

  .tags-table-head,
  .tags-row {
    display: grid;
    grid-template-columns: minmax(220px, 1.5fr) minmax(120px, 1fr) 110px 170px;
    align-items: center;
    gap: 12px;
  }

  .tags-toolbar {
    margin-bottom: 14px;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 12px;
    align-items: center;
  }

  :global(.tags-search) {
    height: 40px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(255, 255, 255, 0.85);
  }

  :global(.tags-search input) {
    font-weight: 700;
    color: #0f172a;
  }

  .tags-sort {
    display: inline-flex;
    gap: 8px;
    align-items: center;
  }

  .tags-sort select {
    height: 34px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(255, 255, 255, 0.75);
    padding: 0 10px;
    font-weight: 700;
    color: #0b1530;
  }

  .tags-table-head {
    padding: 16px 20px;
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #64748b;
    border-bottom: 1px solid rgba(148, 163, 184, 0.3);
  }

  .tags-table-body {
    display: flex;
    flex-direction: column;
  }

  .tags-row {
    padding: 14px 20px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    cursor: pointer;
    transition: background 0.2s ease, box-shadow 0.2s ease;
  }

  .tags-row:hover {
    background: rgba(59, 130, 246, 0.08);
  }

  .tags-row.selected {
    background: rgba(59, 130, 246, 0.12);
    box-shadow: inset 3px 0 0 #2563eb;
  }

  .tag-usage {
    justify-self: end;
    font-weight: 900;
    color: #0b1530;
  }

  .tag-code,
  .tag-updated {
    color: #334155;
    font-weight: 700;
    font-size: var(--b2s-fs-sm);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tag-code {
    font-family: var(--b2s-font-mono);
    letter-spacing: 0.01em;
  }

  .tags-empty {
    padding: 18px 20px;
    color: #64748b;
    font-weight: 700;
  }

  :global(.tags-sort-dir-btn) {
    min-width: 140px;
  }

  /* ---- Modal ---- */







  :global(.tag-modal__body) {
    display: grid;
    gap: 16px;
  }

  .tag-modal__section {
    padding: 0;
    display: grid;
    gap: 8px;
  }

  .tag-modal__section label {
    font-weight: 900;
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
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  }

  .tag-card__title {
    font-weight: 900;
    color: #0b1530;
    margin-bottom: 10px;
  }

  .tag-card--wide {
    margin: 0;
  }

  .tag-card__subtitle {
    margin: -6px 0 12px;
    color: #64748b;
    font-weight: 700;
    font-size: var(--b2s-fs-sm);
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
    color: #64748b;
    font-weight: 800;
    font-size: var(--b2s-fs-sm);
  }

  .tag-input--compact {
    height: 38px;
  }

  .tag-value-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }

  .tag-value-btn {
    height: 44px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid rgba(37, 99, 235, 0.35);
    background: rgba(37, 99, 235, 0.12);
    color: #0b1530;
    font-weight: 900;
    padding: 0 14px;
  }

  .tag-value-pill {
    margin-top: 12px;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: var(--b2s-radius-pill);
    background: #eef2ff;
    border: 1px solid rgba(37, 99, 235, 0.25);
    color: #0b1530;
    font-weight: 900;
  }

  .tag-values-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .tag-value-pill button {
    width: 22px;
    height: 22px;
    border-radius: var(--b2s-radius-pill);
    border: none;
    background: rgba(2, 6, 23, 0.12);
    color: #0b1530;
  }

  .tag-card__hint {
    margin-top: 12px;
    color: #64748b;
    font-weight: 800;
    font-size: var(--b2s-fs-xs);
  }


  @media (max-width: 840px) {
    .tags-page {
      padding: 20px;
    }

    .tags-toolbar {
      grid-template-columns: 1fr;
    }

    .tags-sort {
      width: 100%;
    }

    .tags-sort select,
    .tags-sort :global(.tags-sort-dir-btn) {
      width: 100%;
    }

    .tags-table-head,
    .tags-row {
      grid-template-columns: minmax(160px, 1.4fr) minmax(90px, 0.8fr) 80px 130px;
      gap: 10px;
    }
  }

  @media (max-width: 640px) {
    .tags-table-head,
    .tags-row {
      grid-template-columns: minmax(130px, 1fr) 78px 76px;
    }

    .tags-table-head span:nth-child(2),
    .tags-row .tag-code {
      display: none;
    }

    .tag-updated {
      font-size: var(--b2s-fs-xs);
    }
  }
</style>
