<script lang="ts">
  import { t } from '$lib/i18n';
  import StorageRootDrawerShell from './StorageRootDrawerShell.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import DualListPicker from '$lib/components/ui/DualListPicker.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import { attachTagToStorageRoot, detachTagFromStorageRoot } from '$lib/api/tags';
  import { toggleSetValue } from '$lib/utils/selection';
  import { normalizeTagsCatalog, tagColor, tagId, tagLabel, type UiTag } from '$lib/utils/tags';
  import { toast } from '$lib/stores/toast';
  import type { StorageRootTagLike } from '$lib/utils/storage-roots';

  export let open = false;
  export let storageRootId: number | null = null;
  /** Every tag that can be attached */
  export let catalog: StorageRootTagLike[] = [];
  /** Tags currently attached to the storage root */
  export let currentTags: StorageRootTagLike[] = [];
  export let onClose: () => void;
  /** Called with the new tag set once attach/detach calls succeeded */
  export let onSaved: (tags: StorageRootTagLike[]) => Promise<void> | void = () => {};

  let selectedTagIds: number[] = [];
  let search = '';
  let saving = false;
  let wasOpen = false;

  const validIds = (tags: StorageRootTagLike[]): number[] =>
    tags.map((tag) => tagId(tag)).filter((id) => Number.isFinite(id) && id > 0);

  $: if (open && !wasOpen) {
    wasOpen = true;
    selectedTagIds = validIds(currentTags);
    search = '';
  }
  $: if (!open) wasOpen = false;

  const matches = (tag: UiTag, needle: string) =>
    !needle || [tag.label, tag.name, tag.code].map((v) => String(v ?? '').toLowerCase()).join(' ').includes(needle);

  $: selectedSet = new Set(selectedTagIds);
  $: needle = search.trim().toLowerCase();
  $: catalogTags = normalizeTagsCatalog(catalog);
  $: availableTags = catalogTags.filter((tag) => !selectedSet.has(Number(tag.id)) && matches(tag, needle));
  $: selectedTags = catalogTags.filter((tag) => selectedSet.has(Number(tag.id)) && matches(tag, needle));

  function toggleTag(id: number, checked: boolean) {
    if (!Number.isFinite(id) || id <= 0) return;
    selectedTagIds = [...toggleSetValue(new Set(selectedTagIds), id, checked)];
  }

  async function save() {
    if (saving) return;
    if (!storageRootId) {
      toast.warning(t('No storage root selected'));
      return;
    }
    const wanted = new Set(selectedTagIds.filter((id) => Number.isFinite(id) && id > 0));
    const current = new Set(validIds(currentTags));
    const toAttach = [...wanted].filter((id) => !current.has(id));
    const toDetach = [...current].filter((id) => !wanted.has(id));
    if (toAttach.length === 0 && toDetach.length === 0) {
      toast.warning(t('No tag changes to save'));
      return;
    }

    saving = true;
    try {
      for (const id of toAttach) {
        await attachTagToStorageRoot(fetch, { tag_id: id, resource_id: storageRootId });
      }
      for (const id of toDetach) {
        await detachTagFromStorageRoot(fetch, { tag_id: id, resource_id: storageRootId });
      }
      const tags = catalog
        .filter((tag) => wanted.has(tagId(tag)))
        .map((tag) => ({ ...tag, id: tagId(tag), label: tagLabel(tag), name: tag?.name ?? tag?.label ?? '', color_rgb: tagColor(tag) }));
      await onSaved(tags);
      onClose();
      toast.success(t('Tags updated'));
    } catch {
      toast.error(t('Unable to save tag changes'));
    } finally {
      saving = false;
    }
  }
</script>

<StorageRootDrawerShell
  iconClass="bi bi-tags"
  {open}
  {onClose}
  title={t('Manage tags')}
  subtitle={t('Attach and detach taxonomy tags for the selected storage root.')}
  ariaLabelledby="sr-tags-drawer-title"
  showFooter={true}
>
  <div class="sr-tags-modal-body">
    <p class="b2s-muted">{t('Select the final tag set for this storage root.')}</p>
    <SearchField
      wrapperClass="sr-tag-search"
      placeholder={t('Search tags...')}
      ariaLabel={t('Search tags')}
      bind:value={search}
    />

    <DualListPicker
      availableItems={availableTags}
      selectedItems={selectedTags}
      availableTitle={t('Available tags')}
      selectedTitle={t('Assigned tags')}
      getItemKey={(item) => Number(item?.id ?? 0)}
      itemLabel={(item) => String(item?.label ?? item?.name ?? item?.code ?? '-')}
      on:add={(event) => toggleTag(Number(event.detail.item?.id ?? 0), true)}
      on:remove={(event) => toggleTag(Number(event.detail.item?.id ?? 0), false)}
    >
      <svelte:fragment slot="item" let:item>
        <TagPill label={item.label} color={item.color_rgb ?? null} />
      </svelte:fragment>
    </DualListPicker>
  </div>

  <svelte:fragment slot="footer">
    <div class="sr-modal-actions sr-tags-modal-actions">
      <EntityActionButton variant="secondary" label={t('Cancel')} disabled={saving} onClick={onClose} />
      <EntityActionButton
        variant="primary"
        icon={saving ? 'bi-arrow-repeat' : 'bi-check2'}
        busy={saving}
        label={saving ? t('Saving…') : t('Save tag changes')}
        disabled={saving}
        onClick={save}
      />
    </div>
  </svelte:fragment>
</StorageRootDrawerShell>
