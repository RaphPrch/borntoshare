<script module lang="ts">
  export type EndpointMenuAction = 'test' | 'edit' | 'add-folders' | 'share' | 'delete';
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import ContextMenu, { type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';

  interface Props {
    /** Right-click menu of a file server in the list: test it, edit it, add folders or a share, delete it. */
    endpoint?: Record<string, any> | null;
    at?: any;
    /** Folders attached to it: it cannot be deleted while there are some */
    folderCount?: number;
    testing?: boolean;
    onClose?: () => void;
    onAction?: (kind: EndpointMenuAction, endpoint: Record<string, any>) => void;
  }

  let {
    endpoint = null,
    at = { x: 0, y: 0 },
    folderCount = 0,
    testing = false,
    onClose = () => {},
    onAction = () => {}
  }: Props = $props();

  let inactive = $derived(endpoint ? endpoint.is_active === false || endpoint.is_active === 0 || String(endpoint.status ?? '').toLowerCase() === 'disabled' : false);
  let dfs = $derived(String(endpoint?.type ?? endpoint?.storage_endpoint_type ?? endpoint?.endpoint_type ?? '').toLowerCase() === 'dfs');
  let items = $derived(endpoint
    ? [
        { key: 'test' as const, label: testing ? t('Testing…') : t('Test the connection'), icon: 'bi-activity', disabled: testing, hint: '' },
        { key: 'edit' as const, label: t('Edit'), icon: 'bi-pencil', disabled: false, hint: '' },
        { key: 'add-folders' as const, label: t('Add folders'), icon: 'bi-plus-lg', disabled: inactive, hint: inactive ? t('This file server is disabled') : '' },
        // A DFS namespace has no share of its own
        ...(dfs ? [] : [{ key: 'share' as const, label: t('Create a share'), icon: 'bi-folder-plus', disabled: inactive, hint: inactive ? t('This file server is disabled') : '' }]),
        {
          key: 'delete' as const,
          label: t('Delete storage endpoint'),
          icon: 'bi-trash',
          danger: true,
          disabled: folderCount > 0,
          hint: folderCount > 0 ? t('{count} folder(s) attached: remove them from BornToShare first', { count: folderCount }) : ''
        }
      ]
    : []);
  // The shared menu draws it; the delete entry stands apart
  let menuItems = $derived(items.map((item) => ({ ...item, separated: item.key === 'delete' }) as ContextMenuItem));

  function pick(key: string) {
    // The target first: closing the menu clears `endpoint` (the parent owns it)
    if (endpoint) onAction(key as EndpointMenuAction, endpoint);
  }
</script>

<ContextMenu open={Boolean(endpoint)} title={String(endpoint?.name ?? '')} subtitle={inactive ? t('Disabled') : ''}
  items={menuItems} {at} {onClose} onPick={pick} />
