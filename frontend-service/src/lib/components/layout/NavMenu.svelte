<script lang="ts">
  import { fly, fade } from 'svelte/transition';
  import { t } from '$lib/i18n';
  import { dur, MOTION } from '$lib/utils/motion';
  import type { NavSection } from './nav';

  /**
   * The ☰ menu: a panel over the page, under the top bar. The same sections and entries as before (Workspace,
   * Governance, Storage Intelligence, Administration), each entry with its pages (tabs) below it, then the pages
   * opened lately. Closes on Escape, a click outside or a choice.
   */
  interface Props {
    open: boolean;
    sections: NavSection[];
    current: string;
    currentTab: string;
    recent: Array<{ href: string; label: string }>;
    onClose: () => void;
  }

  let { open, sections, current, currentTab, recent, onClose }: Props = $props();
  const badge = (count: number) => (count > 99 ? '99+' : String(count));
  let panel = $state<HTMLElement | null>(null);
  $effect(() => {
    if (open) queueMicrotask(() => panel?.querySelector<HTMLElement>('a[aria-current="page"], a')?.focus());
  });
</script>

<svelte:window onkeydown={(event) => open && event.key === 'Escape' && onClose()} />

{#if open}
  <button type="button" class="nm__backdrop" aria-label={t('Close the menu')} onclick={onClose} transition:fade={{ duration: dur(MOTION.fast) }}></button>
  <nav class="nm" aria-label={t('Main navigation')} bind:this={panel} transition:fly={{ x: -24, duration: dur(MOTION.base) }}>
    {#each sections as section (section.key)}
      <div class="nm__sec">{section.label}</div>
      {#each section.items as item (item.href)}
        <a href={item.href} class="nm__item" class:on={current === item.href} aria-current={current === item.href ? 'page' : undefined} onclick={onClose}>
          <i class={`bi ${item.icon}`} aria-hidden="true"></i>
          <span>{item.label}</span>
          {#if item.count}<b class="nm__badge" class:is-danger={item.danger}>{badge(item.count)}</b>{/if}
        </a>
        {#if item.tabs && item.tabs.length > 1}
          {#each item.tabs.filter((tab) => tab.menu !== false) as tab (tab.href)}
            <a href={tab.href} class="nm__sub" class:on={current === item.href && currentTab === tab.href} onclick={onClose}>{tab.label}</a>
          {/each}
        {/if}
      {/each}
    {/each}
    {#if recent.length}
      <div class="nm__recent">
        <div class="nm__sec">{t('Recent')}</div>
        {#each recent as page (page.href)}
          <a href={page.href} class="nm__sub nm__sub--recent" onclick={onClose}>{page.label}</a>
        {/each}
      </div>
    {/if}
  </nav>
{/if}

<style>
  .nm__backdrop { position: fixed; inset: 52px 0 0 0; z-index: 70; border: 0; padding: 0; background: rgba(18, 59, 73, 0.32); cursor: default; }
  .nm { position: fixed; top: 52px; left: 0; bottom: 0; z-index: 71; width: 320px; display: flex; flex-direction: column; gap: 1px; padding: 12px; overflow-y: auto;
    background: #fff; box-shadow: 12px 0 32px rgba(18, 59, 73, 0.18); }
  .nm__sec { padding: 14px 10px 6px; color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .nm__item { display: flex; align-items: center; gap: 10px; min-height: 36px; padding: 0 10px; border-radius: 8px; color: var(--b2s-color-text); font-size: 14px; text-decoration: none; }
  .nm__item i { width: 18px; font-size: 16px; text-align: center; }
  .nm__item:hover, .nm__sub:hover { background: var(--b2s-color-neutral-soft); }
  .nm__item.on { background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); font-weight: 600; box-shadow: inset 3px 0 0 var(--b2s-accent-vivid); }
  .nm__item:focus-visible, .nm__sub:focus-visible { outline: 2px solid var(--b2s-accent-vivid); outline-offset: 1px; }
  .nm__badge { margin-left: auto; min-width: 20px; padding: 0 7px; border-radius: 999px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-soft);
    font-size: 11px; font-weight: 700; line-height: 18px; text-align: center; }
  .nm__item.on .nm__badge { background: var(--b2s-accent); color: #fff; }
  .nm__badge.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .nm__sub { display: block; padding: 5px 10px 5px 38px; border-radius: 8px; color: var(--b2s-color-text-muted); font-size: 13px; text-decoration: none; }
  .nm__sub.on { color: var(--b2s-color-text); font-weight: 600; }
  .nm__recent { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--b2s-color-border-soft); }
  .nm__sub--recent { padding-left: 10px; color: var(--b2s-color-text); }
  .nm__item, .nm__sub { transition: background-color var(--b2s-motion-fast) var(--b2s-ease-out), color var(--b2s-motion-fast) var(--b2s-ease-out), box-shadow var(--b2s-motion-fast) var(--b2s-ease-out); }
</style>
