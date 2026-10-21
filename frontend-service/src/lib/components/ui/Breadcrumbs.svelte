<script lang="ts">
  import { t } from '$lib/i18n';

  /** Trail shown above a detail page; the last item is the current page (no link). */
  export let items: { label: string; href?: string }[] = [];
</script>

<nav class="b2s-breadcrumbs" aria-label={t('Breadcrumb')}>
  <ol>
    {#each items as item, index}
      <li>
        {#if item.href && index < items.length - 1}
          <a href={item.href}>{item.label}</a>
        {:else}
          <span aria-current={index === items.length - 1 ? 'page' : undefined}>{item.label}</span>
        {/if}
      </li>
    {/each}
  </ol>
</nav>

<style>
  .b2s-breadcrumbs ol {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin: 0 0 12px;
    padding: 0;
    list-style: none;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .b2s-breadcrumbs li + li::before {
    content: '/';
    margin-right: 6px;
    color: #cbd5e1;
  }

  .b2s-breadcrumbs a {
    color: var(--b2s-color-text-muted);
    text-decoration: none;
  }

  .b2s-breadcrumbs a:hover {
    color: var(--b2s-color-text);
    text-decoration: underline;
  }

  .b2s-breadcrumbs span {
    color: var(--b2s-color-text);
    font-weight: 500;
  }
</style>
