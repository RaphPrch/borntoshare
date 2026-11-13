<script lang="ts">
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  /** The options of the 5S menu: the scores, and the scanner of the module */
  let path = $derived($page.url.pathname);
  const items = [
    { href: '/five-s', label: () => t('Overview'), icon: 'bi-stars' },
    { href: '/five-s/scanner', label: () => t('Scanner'), icon: 'bi-radar' }
  ];
</script>

<nav class="ft5" aria-label={t('5S')}>
  {#each items as item (item.href)}
    <a href={item.href} class:is-on={path === item.href} aria-current={path === item.href ? 'page' : undefined}><i class={`bi ${item.icon}`} aria-hidden="true"></i>{item.label()}</a>
  {/each}
</nav>

<style>
  .ft5 { display: inline-flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--b2s-color-neutral-soft); align-self: flex-start; }
  .ft5 a { display: inline-flex; gap: 8px; align-items: center; padding: 7px 14px; border-radius: 9px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); font-weight: 600; text-decoration: none; transition: background-color var(--b2s-motion-fast), color var(--b2s-motion-fast); }
  .ft5 a.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
</style>
