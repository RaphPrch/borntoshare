<script lang="ts">
  import EntitySidebarTree, { type EntityTreeNode } from '$lib/components/entity/EntitySidebarTree.svelte';
  import { t } from '$lib/i18n';
  import type { IdentitySourceCardVM } from '$lib/mappers/identity-sources.mapper';

  
  interface Props {
    /** List pane of the Directories page: the directories grouped by kind, those to look at marked. */
    cards?: IdentitySourceCardVM[];
    selectedId?: number | null;
    query?: string;
    onSelect?: (id: number) => void;
    onQueryChange?: (value: string) => void;
    onAdd?: (() => void) | null;
  }

  let {
    cards = [],
    selectedId = null,
    query = '',
    onSelect = () => {},
    onQueryChange = () => {},
    onAdd = null
  }: Props = $props();

  let filter = $state('all');
  const toReview = (card: IdentitySourceCardVM) =>
    card.isEnabled && (card.healthTone === 'error' || card.snapshotTone === 'error' || (card.supportsSnapshot && card.neverSynced) || Boolean(card.lastProbeStale));
  const dot = (card: IdentitySourceCardVM): EntityTreeNode['dot'] =>
    !card.isEnabled ? null : card.healthTone === 'error' || card.snapshotTone === 'error' ? 'error' : toReview(card) ? 'warning' : null;
  const keep = (card: IdentitySourceCardVM, key: string) => key === 'all' || (key === 'review' ? toReview(card) : !card.isEnabled);

  let filters = $derived([
    { key: 'all', label: t('All'), count: cards.length },
    { key: 'review', label: t('To review'), count: cards.filter(toReview).length },
    { key: 'disabled', label: t('Disabled'), count: cards.filter((card) => !card.isEnabled).length }
  ]);
  let kinds = $derived([
    { key: 'directory', label: t('Active Directory / LDAP'), icon: 'bi-diagram-3', match: (card: IdentitySourceCardVM) => !card.isLocal },
    { key: 'local', label: t('Local accounts'), icon: 'bi-person-lock', match: (card: IdentitySourceCardVM) => card.isLocal }
  ]);
  let nodes = $derived(kinds
    .map((kind): EntityTreeNode => {
      const items = cards.filter((card) => kind.match(card) && keep(card, filter)).sort((a, b) => a.name.localeCompare(b.name, 'fr', { numeric: true }));
      return {
        key: `kind:${kind.key}`,
        label: kind.label,
        icon: kind.icon,
        iconTone: 'zone',
        badges: [{ label: String(items.length), title: t('{count} directories', { count: items.length }) }],
        children: items.map((card) => ({
          key: `src:${card.id}`,
          label: card.name,
          subtitle: card.isLocal ? t('Local provider') : String((card.raw as any)?.domain_name || card.endpointLabel || ''),
          icon: card.isLocal ? 'bi-person-lock' : 'bi-diagram-3',
          iconTone: 'server',
          selectId: card.id,
          dot: dot(card),
          badges: card.isEnabled ? [] : [{ label: t('Disabled'), tone: 'neutral' }],
          searchText: `${card.endpointLabel} ${(card.raw as any)?.base_dn ?? ''} ${card.bindDn}`
        }))
      };
    })
    .filter((node) => (node.children ?? []).length > 0));
</script>

<EntitySidebarTree
  {onAdd}
  addLabel={t('New directory')}
  ariaLabel={t('Directories')}
  searchPlaceholder={t('Name, domain, host…')}
  searchAriaLabel={t('Search a directory')}
  emptyLabel={t('No directory matches your search.')}
  {query}
  {nodes}
  {selectedId}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  storageKey="b2s.identitySources.tree"
  defaultExpandDepth={1}
  {onQueryChange}
  onSelect={(id) => onSelect(Number(id))}
/>
