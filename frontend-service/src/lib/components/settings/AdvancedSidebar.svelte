<script module lang="ts">
  export type NavItem = {
    key: string;
    label: string;
    icon: string;
    badge?: string;
    badgeVariant?: 'default' | 'new';
  };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  interface Props {
    current: string;
    items: NavItem[];
    basePath?: string;
  }

  let { current, items, basePath = '/admin/advanced-settings' }: Props = $props();

  function href(key: string) {
    return `${basePath}/${key}`;
  }
</script>

<aside class="b2s-adv-sidebar">
  <div class="title">{t('Sections')}</div>
  <nav>
    {#each items as item}
      <a class:active={current === item.key} href={href(item.key)} aria-current={current === item.key ? 'page' : undefined}>
        <i class={'bi ' + item.icon} aria-hidden="true"></i>
        <span class="item-label">{item.label}</span>
        {#if item.badge}
          <span class={['b2s-adv-sidebar-badge', item.badgeVariant === 'new' ? 'is-new' : ''].filter(Boolean).join(' ')}>{item.badge}</span>
        {/if}
      </a>
    {/each}
  </nav>
</aside>
