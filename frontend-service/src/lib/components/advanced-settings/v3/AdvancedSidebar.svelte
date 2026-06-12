<script lang="ts">
  export type NavItem = {
    key: string;
    label: string;
    icon: string;
    badge?: string;
    badgeVariant?: 'default' | 'new';
  };

  export let current: string;
  export let items: NavItem[];
  export let basePath: string = '/admin/advanced-settings';

  function href(key: string) {
    return `${basePath}/${key}`;
  }
</script>

<aside class="b2s-adv-sidebar">
  <div class="title">Sections</div>
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
