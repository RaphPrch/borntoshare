<script lang="ts">
  import EntitySidebarTree, { type EntityTreeNode } from '$lib/components/entity/EntitySidebarTree.svelte';
  import { t } from '$lib/i18n';

  /**
   * List pane of the Identities page, grouped by what people do: administrators, guardians, users, directory groups.
   * A guardian without an e-mail is marked: the requests to validate never reach them.
   */
  type Item = Record<string, any>;
  export let items: Item[] = [];
  export let guardians: Record<number, { folders: number; sole: number }> = {};
  export let selectedKey: string | null = null;
  export let query = '';
  export let onSelect: (key: string) => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};
  export let onAdd: (() => void) | null = null;
  export let onOpenAdmins: () => void = () => {};

  let filter = 'all';
  const isGroup = (item: Item) => String(item?.type ?? '').toLowerCase() === 'group';
  const isAdmin = (item: Item) => Boolean(item?.is_admin) || (Array.isArray(item?.roles) && item.roles.includes('platform_admin'));
  const active = (item: Item) => item?.is_active !== false && String(item?.status ?? 'active').toLowerCase() !== 'inactive';
  const hasMail = (item: Item) => Boolean(String(item?.email ?? '').trim());
  const guarded = (item: Item) => (isGroup(item) ? 0 : guardians[Number(item?.id)]?.folders ?? 0);
  const toReview = (item: Item) => !isGroup(item) && active(item) && guarded(item) > 0 && !hasMail(item);
  const keep = (item: Item, key: string) =>
    key === 'all' || (key === 'review' ? toReview(item) : key === 'nomail' ? !isGroup(item) && !hasMail(item) : !active(item));
  const keyOf = (item: Item) => `${isGroup(item) ? 'group' : 'user'}:${item?.id}`;
  const nameOf = (item: Item) => String(item?.display_name || item?.username || item?.name || '—');

  $: filters = [
    { key: 'all', label: t('All'), count: items.length },
    { key: 'review', label: t('To review'), count: items.filter(toReview).length },
    { key: 'nomail', label: t('Without e-mail'), count: items.filter((item) => !isGroup(item) && !hasMail(item)).length },
    { key: 'inactive', label: t('Inactive'), count: items.filter((item) => !active(item)).length }
  ].filter((item) => item.key === 'all' || item.count > 0);

  const KINDS = () => [
    { key: 'admins', label: t('Administrators'), icon: 'bi-shield-lock', match: (item: Item) => isAdmin(item) },
    { key: 'guardians', label: t('Guardians'), icon: 'bi-person-check', match: (item: Item) => !isAdmin(item) && guarded(item) > 0 },
    { key: 'users', label: t('Users'), icon: 'bi-person', match: (item: Item) => !isAdmin(item) && !isGroup(item) && guarded(item) === 0 },
    { key: 'groups', label: t('Directory groups'), icon: 'bi-people', match: (item: Item) => !isAdmin(item) && isGroup(item) }
  ];
  function subtitle(item: Item): string {
    if (isGroup(item)) return t('group · {source}', { source: item?.source_name ?? '' });
    const folders = guarded(item);
    const source = String(item?.source_name ?? '');
    return folders ? t('{count} folder(s) · {source}', { count: folders, source }) : item?.username && nameOf(item) !== item.username ? `${item.username} · ${source}` : source;
  }

  $: nodes = KINDS()
    .map((kind): EntityTreeNode => {
      const list = items.filter((item) => kind.match(item) && keep(item, filter)).sort((a, b) => nameOf(a).localeCompare(nameOf(b), 'fr'));
      return {
        key: `kind:${kind.key}`,
        label: kind.label,
        icon: kind.icon,
        iconTone: 'zone',
        badges: [{ label: String(list.length) }],
        children: list.map((item) => ({
          key: keyOf(item),
          label: nameOf(item),
          subtitle: subtitle(item),
          icon: isGroup(item) ? 'bi-people' : String(item?.auth_source ?? item?.source ?? '') === 'local' ? 'bi-person-lock' : 'bi-person',
          iconTone: 'root',
          selectId: keyOf(item),
          dot: toReview(item) ? 'warning' : null,
          badges: active(item) ? [] : [{ label: t('Inactive'), tone: 'neutral' }],
          searchText: `${item?.username ?? ''} ${item?.email ?? ''} ${item?.source_name ?? ''}`
        }))
      };
    })
    .filter((node) => (node.children ?? []).length > 0);
</script>

<EntitySidebarTree
  {onAdd}
  addLabel={t('Add an identity')}
  ariaLabel={t('Identities')}
  searchPlaceholder={t('Name, login, e-mail…')}
  searchAriaLabel={t('Search an identity')}
  emptyLabel={t('No identity matches your search.')}
  {query}
  {nodes}
  selectedId={selectedKey}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  storageKey="b2s.identities.tree"
  defaultExpandDepth={1}
  {onQueryChange}
  onSelect={(id) => onSelect(String(id))}
>
  <div slot="below-search" class="ids-admins">
    <button type="button" class="b2s-link-btn" on:click={onOpenAdmins}><i class="bi bi-diagram-3" aria-hidden="true"></i>{t('Who administers BornToShare')}</button>
  </div>
</EntitySidebarTree>

<style>
  .ids-admins { margin: -4px 0 8px; }
  .ids-admins .b2s-link-btn { display: inline-flex; gap: 6px; align-items: center; font-size: var(--b2s-fs-xs); }
</style>
