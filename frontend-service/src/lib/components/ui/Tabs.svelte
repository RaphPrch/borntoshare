<script module lang="ts">
  export type TabItem<Key extends string = string> = {
    key: Key;
    label: string;
    icon?: string | null;
  };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  export let tabs: TabItem[] = [];
  export let activeKey = '';
  export let onChange: ((key: string) => void) | null = null;
  export let ariaLabel = t('Sections');
</script>

<nav class="b2s-tabs" aria-label={ariaLabel}>
  {#each tabs as tab (tab.key)}
    <button
      type="button"
      class:is-active={tab.key === activeKey}
      aria-current={tab.key === activeKey ? 'page' : undefined}
      on:click={() => onChange?.(tab.key)}
    >
      {#if tab.icon}
        <i class={`bi ${tab.icon}`} aria-hidden="true"></i>
      {/if}
      {tab.label}
    </button>
  {/each}
</nav>

<style>
  .b2s-tabs {
    border-bottom: 1px solid var(--b2s-border, #dce5f2);
    display: flex;
    align-items: center;
    gap: 24px;
    overflow-x: auto;
  }

  .b2s-tabs button {
    min-height: 49px;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--b2s-color-text-muted, #60718f);
    font-size: var(--b2s-fs-lg);
    font-weight: 650;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0 4px;
    white-space: nowrap;
  }

  .b2s-tabs button.is-active {
    color: var(--b2s-topbar-bg, #111b3f);
    border-bottom-color: var(--b2s-topbar-accent, #4da3ff);
  }
</style>
