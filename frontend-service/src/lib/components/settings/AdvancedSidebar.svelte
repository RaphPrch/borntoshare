<script module lang="ts">
  export type NavItem = {
    key: string;
    label: string;
    icon: string;
    /** Heading of the group the item opens (Général, Sécurité…) */
    group?: string;
    /** A tab of the page (« tab=workers »): the item is current only on that tab */
    query?: string;
    badge?: string;
    badgeVariant?: 'default' | 'new';
  };
</script>

<script lang="ts">
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  interface Props {
    current: string;
    items: NavItem[];
    basePath?: string;
  }

  let { current, items, basePath = '/admin/advanced-settings' }: Props = $props();

  const href = (item: NavItem) => `${basePath}/${item.key}${item.query ? `?${item.query}` : ''}`;
  // On a page that also has a tab of its own in the list (Infrastructure › Workers), the tab decides
  const isCurrent = (item: NavItem) => {
    if (current !== item.key) return false;
    const tabbed = items.filter((other) => other.key === item.key && other.query);
    if (item.query) return $page.url.search.includes(item.query);
    return !tabbed.some((other) => $page.url.search.includes(other.query ?? '\u0000'));
  };
</script>

<aside class="b2s-adv-sidebar">
  <nav>
    {#each items as item (item.key + (item.query ?? ''))}
      {#if item.group}<div class="title">{item.group}</div>{/if}
      <a class:active={isCurrent(item)} href={href(item)} aria-current={isCurrent(item) ? 'page' : undefined}>
        <i class={'bi ' + item.icon} aria-hidden="true"></i>
        <span class="item-label">{item.label}</span>
        {#if item.badge}
          <span class={['b2s-adv-sidebar-badge', item.badgeVariant === 'new' ? 'is-new' : ''].filter(Boolean).join(' ')}>{item.badge}</span>
        {/if}
      </a>
    {/each}
  </nav>
  <span class="visually-hidden">{t('Sections')}</span>
</aside>
