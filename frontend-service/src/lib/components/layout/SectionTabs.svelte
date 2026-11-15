<script module lang="ts">
  export type SectionTab = { href: string; label: string; /** Paths that belong to the tab, besides its href */ also?: string[]; count?: number };
</script>

<script lang="ts">
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  interface Props {
    /** Underlined tabs at the top of a menu entry gathering several pages (Access Management: requests, exposure…). */
    tabs: SectionTab[];
    label?: string;
  }

  let { tabs, label = '' }: Props = $props();
  const covers = (prefix: string, path: string) => path === prefix || path.startsWith(`${prefix}/`);
  // The longest matching prefix wins (« /admin/identity/admins » before « /admin/identity »)
  let current = $derived.by(() => {
    let best = { href: '', length: -1 };
    for (const tab of tabs) {
      for (const prefix of [tab.href, ...(tab.also ?? [])]) {
        if (covers(prefix, $page.url.pathname) && prefix.length > best.length) best = { href: tab.href, length: prefix.length };
      }
    }
    return best.href;
  });
</script>

{#if tabs.length > 1}
  <nav class="v2-tabs sect" aria-label={label || t('Sections')}>
    {#each tabs as tab (tab.href)}
      <a href={tab.href} class:is-on={current === tab.href} aria-current={current === tab.href ? 'page' : undefined}>{tab.label}{#if tab.count}<b>{tab.count}</b>{/if}</a>
    {/each}
  </nav>
{/if}

<style>
  .sect { margin-bottom: 4px; }
</style>
