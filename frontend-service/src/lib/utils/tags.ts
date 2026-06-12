export type UiTag = {
  id: number;
  label: string;
  name?: string | null;
  code?: string | null;
  color_rgb?: string | null;
};

export const tagId = (tag: any): number => Number(tag?.id ?? tag?.tag_id ?? 0);

export const tagLabel = (tag: any): string =>
  String(tag?.label ?? tag?.name ?? tag?.code ?? '').trim() || `Tag #${tagId(tag)}`;

export const tagColor = (tag: any): string | null => {
  const raw = String(tag?.color_rgb ?? tag?.color ?? '').trim();
  return raw || null;
};

export const normalizeTagsCatalog = (tags: any[]): UiTag[] =>
  (Array.isArray(tags) ? tags : [])
    .map((tag: any) => ({
      ...tag,
      id: tagId(tag),
      label: tagLabel(tag),
      color_rgb: tagColor(tag)
    }))
    .filter((tag: UiTag) => Number.isFinite(tag.id) && tag.id > 0)
    .sort((a: UiTag, b: UiTag) => String(a.label).localeCompare(String(b.label), 'fr', { sensitivity: 'base' }));

