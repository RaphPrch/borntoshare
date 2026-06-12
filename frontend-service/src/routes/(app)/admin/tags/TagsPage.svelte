<script lang="ts">
  import { invalidateAll } from "$app/navigation";

  import ConfirmDeleteDialog from "$lib/components/common/ConfirmDeleteDialog.svelte";
  import EntityActionButton from "$lib/components/common/EntityActionButton.svelte";
  import EntityActionGroup, { type EntityActionItem } from "$lib/components/common/EntityActionGroup.svelte";
  import SearchField from "$lib/components/common/SearchField.svelte";
  import TagPill from "$lib/components/tags/TagPill.svelte";
  import EmptyState from "$lib/components/ui/EmptyState.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import { createTag, updateTag, deleteTag, type TagOverview } from "$lib/api/tags";
  import { showApiErrorToast } from "$lib/core/errors/api-toast";
  import { toast } from "$lib/utils/toast";
  import {
    dependencyCountDeleteMessage,
    dependencyDeleteMessage,
    isDependencyDeleteError
  } from "$lib/utils/delete-guard";

  export let data: {
    tags: Array<(TagOverview & { usage?: number } & { color?: string | null })>;
  };

  const getUsage = (tag: any) => (typeof tag?.usage === "number" ? tag.usage : 0);

  // Normalize DAL shape (id,name,color,usage) into UI shape (label,color_rgb)
  // so TagPill + modal edition always work.
  $: tagsNorm = (data.tags ?? []).map((t: any) => ({
    ...t,
    label: t.label ?? t.name ?? t.code ?? "Tag",
    color_rgb: t.color_rgb ?? t.color ?? null
  }));

  let selectedId: number | null = null;
  $: selectedTag = tagsNorm.find((t) => t.id === selectedId) ?? null;

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
    return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  const normalizeText = (value: unknown) => String(value ?? "").toLowerCase().trim();

  $: hasNameError = !form.name.trim();
  $: hasColorError = !isValidHexColor(form.color_rgb);
  $: canSubmit = !busy && !hasNameError && !hasColorError;

  $: filteredTags = tagsNorm.filter((t: any) => {
    const q = normalizeText(searchQuery);
    if (!q) return true;
    const haystack = [t?.label, t?.name, t?.code, t?.value_text]
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
      label: "Create tag",
      icon: "bi-plus-lg",
      variant: "primary",
      onClick: openCreate
    },
    {
      key: "edit",
      label: "Edit tag",
      icon: "bi-pencil-square",
      variant: "secondary",
      disabled: !selectedTag,
      onClick: openEdit
    },
    {
      key: "delete",
      label: "Delete tag",
      icon: "bi-trash",
      variant: "danger",
      disabled: !selectedTag || getUsage(selectedTag) > 0,
      title: !selectedTag
        ? 'Select a tag first'
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
        toast.success("Tag created.");
      } else if (modalMode === "edit" && selectedTag) {
        await updateTag(fetch, selectedTag.id, { name, label, code, color_rgb, color, value_text });
        toast.success("Tag updated.");
      }

      modalOpen = false;
      await invalidateAll();
    } catch (e) {
      errorMsg = e?.message ?? "Operation failed.";
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
      toast.success("Tag deleted.");
      showDeleteConfirm = false;
      selectedId = null;
      await invalidateAll();
    } catch (e) {
      const msg = e?.message ?? "Delete failed.";
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
  <PageHeader title="Tags" subtitle="All created tags are listed here.">
    <svelte:fragment slot="actions">
      <EntityActionGroup actions={tagActions} ariaLabel="Tag actions" />
    </svelte:fragment>
  </PageHeader>

  <section class="tags-toolbar">
    <SearchField
      wrapperClass="tags-search"
      placeholder="Search by name, code, or value"
      ariaLabel="Search for a tag"
      bind:value={searchQuery}
    />
    <div class="tags-sort">
      <select bind:value={sortBy}>
        <option value="name">Trier: Nom</option>
        <option value="usage">Trier: Usage</option>
        <option value="updated">Sort: Last updated</option>
      </select>
      <EntityActionButton
        variant="secondary"
        icon={sortDir === 'asc' ? 'bi-sort-down' : 'bi-sort-up'}
        label={sortDir === 'asc' ? 'Ascending' : 'Descending'}
        className="tags-sort-dir-btn"
        onClick={() => (sortDir = sortDir === 'asc' ? 'desc' : 'asc')}
      />
    </div>
  </section>

  <section class="tags-table">
    <div class="tags-table-head">
      <span>Tag</span>
      <span>Code</span>
      <span>Usage</span>
      <span>Updated</span>
    </div>

    <div class="tags-table-body">
      {#if Array.isArray(sortedTags) && sortedTags.length}
        {#each sortedTags as tag, index (tag.id)}
          <div
            class="tags-row"
            class:selected={tag.id === selectedId}
            role="button"
            tabindex="0"
            aria-selected={tag.id === selectedId}
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
              <TagPill label={tag.label ?? tag.name ?? tag.code ?? 'Tag'} color={tag.color_rgb ?? null} />
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
            title="No tags found"
            description="Create a tag or adjust your search."
            actionLabel="Create tag"
            onAction={openCreate}
          />
        </div>
      {/if}
    </div>
  </section>
</section>

{#if modalOpen}
  <div
    class="tag-modal-backdrop"
    role="button"
    tabindex="0"
    aria-label="Close dialog"
    on:click={() => (modalOpen = false)}
    on:keydown={(e) =>
      (e.key === "Enter" || e.key === " ") && (e.preventDefault(), (modalOpen = false))
    }
  >
    <div
      class="tag-modal"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      on:click|stopPropagation
      on:keydown|stopPropagation
    >
      <header class="tag-modal__header">
        <div>
          <h2>{modalMode === "create" ? "Create tag" : "Edit tag"}</h2>
          <p>Define and create a customizable tag for your resources.</p>
        </div>
        <button
          class="tag-modal__close"
          type="button"
          aria-label="Close"
          on:click={() => (modalOpen = false)}
        >
          ×
        </button>
      </header>

      <section class="tag-modal__section">
          <label for="tag-name">Tag name</label>
          <input
            id="tag-name"
            class="tag-input"
            placeholder="e.g. Sensitive"
            bind:value={form.name}
          />
      </section>

      <section class="tag-modal__grid">
          <div class="tag-card">
            <div class="tag-card__title">Tag color</div>
            <div class="tag-palette">
              {#each palette as color}
                <button
                  type="button"
                  class="tag-swatch"
                  class:active={form.color_rgb === color}
                  style={`background:${color}`}
                  on:click={() => (form.color_rgb = color)}
                  aria-label={`Color ${color}`}
                ></button>
              {/each}
            </div>
            <div class="tag-custom">
              <span class="tag-custom__label">Custom…</span>
              <input
                class="tag-input tag-input--compact"
                placeholder="#3fa9f5"
                bind:value={form.color_rgb}
              />
            </div>
          </div>
      </section>

      <section class="tag-card tag-card--wide">
          <div class="tag-card__title">Value</div>
          <p class="tag-card__subtitle">Create one or more predefined values for this tag</p>
          <div class="tag-value-row">
            <input
              class="tag-input"
              placeholder="e.g. Confidential"
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
              Add value
            </button>
          </div>
          {#if valueItems.length > 0}
            <div class="tag-values-list">
              {#each valueItems as item (item)}
                <div class="tag-value-pill">
                  {item}
                  <button
                    type="button"
                    aria-label="Remove value"
                    on:click={() => removeValueItem(item)}
                  >
                    ×
                  </button>
                </div>
              {/each}
            </div>
          {/if}
          <div class="tag-card__hint">Suggested: Public, Sensitive, Private, Archived</div>
      </section>

      {#if errorMsg}
        <div class="tag-modal__error">{errorMsg}</div>
      {/if}

      <footer class="tag-modal__footer">
        <EntityActionButton variant="ghost" label="Cancel" onClick={() => (modalOpen = false)} />
        <EntityActionButton
          variant="primary"
          busy={busy}
          label={modalMode === "create" ? "Create" : "Save changes"}
          onClick={handleSubmit}
        />
      </footer>
    </div>
  </div>
{/if}

<ConfirmDeleteDialog
  open={showDeleteConfirm}
  onClose={closeDeleteConfirm}
  onConfirm={handleDelete}
  ariaLabelledby="tags-delete-modal-title"
  title="Delete tag"
  description={selectedTag?.label ?? selectedTag?.name ?? null}
  impactTitle="Consequences"
  impactItems={[
    'Irreversible deletion of this tag.',
    'Associated governance references must be recreated if needed.'
  ]}
  deleteLabel="Delete"
  deleteBusyLabel="Deleting…"
  busy={busy}
  requireTextConfirm={true}
  requiredText="DELETE"
  textConfirmLabel="Type"
  textConfirmPlaceholder="DELETE"
/>

<style>
  :global(.b2s-app-root main) {
    padding: 0 !important;
  }

  .tags-page {
    min-height: calc(100vh - 64px);
    padding: 28px 36px 40px;
    color: #0f172a;
  }

  :global(.tags-page .b2s-page-header__actions .b2s-action-group) {
    width: auto;
  }

  :global(.tags-page .b2s-tag-pill) {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12px;
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
    border-radius: 18px;
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
    border-radius: 12px;
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
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(255, 255, 255, 0.75);
    padding: 0 10px;
    font-weight: 700;
    color: #0b1530;
  }

  .tags-table-head {
    padding: 16px 20px;
    font-size: 12px;
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
    font-size: 13px;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tag-code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
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
  .tag-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.55);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }

  .tag-modal {
    width: min(760px, 100%);
    background: #ffffff;
    border-radius: 18px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    box-shadow: 0 30px 60px rgba(0, 0, 0, 0.35);
    overflow: hidden;
  }

  .tag-modal__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding: 18px 20px;
    background: #f8fafc;
    border-bottom: 1px solid rgba(148, 163, 184, 0.25);
  }

  .tag-modal__header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 900;
    color: #0b1530;
  }

  .tag-modal__header p {
    margin: 6px 0 0;
    color: #64748b;
    font-weight: 700;
    font-size: 13px;
  }

  .tag-modal__close {
    border: none;
    background: transparent;
    width: 36px;
    height: 36px;
    border-radius: 12px;
    font-size: 22px;
    line-height: 1;
    color: #64748b;
  }

  .tag-modal__close:hover {
    background: rgba(37, 99, 235, 0.10);
  }

  .tag-modal__section {
    padding: 18px 20px 0;
    display: grid;
    gap: 8px;
  }

  .tag-modal__section label {
    font-weight: 900;
    color: #0b1530;
    font-size: 13px;
  }

  .tag-input {
    height: 44px;
    border-radius: 12px;
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
    padding: 14px 20px 0;
  }

  .tag-card {
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 16px;
    padding: 14px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  }

  .tag-card__title {
    font-weight: 900;
    color: #0b1530;
    margin-bottom: 10px;
  }

  .tag-card--wide {
    margin: 14px 20px 0;
  }

  .tag-card__subtitle {
    margin: -6px 0 12px;
    color: #64748b;
    font-weight: 700;
    font-size: 13px;
  }

  .tag-palette {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  .tag-swatch {
    width: 26px;
    height: 26px;
    border-radius: 999px;
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
    font-size: 13px;
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
    border-radius: 12px;
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
    border-radius: 999px;
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
    border-radius: 999px;
    border: none;
    background: rgba(2, 6, 23, 0.12);
    color: #0b1530;
  }

  .tag-card__hint {
    margin-top: 12px;
    color: #64748b;
    font-weight: 800;
    font-size: 12px;
  }

  .tag-modal__error {
    margin: 14px 20px 0;
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(239, 68, 68, 0.10);
    color: #b91c1c;
    border: 1px solid rgba(239, 68, 68, 0.25);
    font-weight: 800;
  }

  .tag-modal__footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding: 16px 20px 18px;
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
      font-size: 12px;
    }
  }
</style>
