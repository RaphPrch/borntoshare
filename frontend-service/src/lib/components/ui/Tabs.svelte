<script module lang="ts">
  export type TabItem<Key extends string = string> = {
    key: Key;
    label: string;
    icon?: string | null;
    count?: number | null;
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
      {#if tab.count !== undefined && tab.count !== null}<span class="b2s-tabs__count">{tab.count}</span>{/if}
    </button>
  {/each}
</nav>

<style>
  .b2s-tabs {
    display: flex;
    align-items: center;
    gap: 4px;
    border-bottom: 1px solid #e5eaf3;
    overflow-x: auto;
  }

  .b2s-tabs button {
    min-height: 44px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0 14px;
    border: none;
    background: transparent;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-md);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }

  .b2s-tabs button:hover {
    color: var(--b2s-color-text);
  }

  .b2s-tabs button.is-active {
    color: var(--b2s-color-text);
    font-weight: 600;
    box-shadow: inset 0 -2px 0 var(--b2s-topbar-bg);
  }

  .b2s-tabs__count {
    padding: 0 7px;
    border-radius: var(--b2s-radius-pill);
    background: #eef2f7;
    color: #475569;
    font-size: 11px;
    font-weight: 600;
  }
</style>
