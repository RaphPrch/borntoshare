<script lang="ts">
  export type TabItem = { key: string; label: string };

  export let tabs: TabItem[] = [];
  export let activeKey = "";
  export let onChange: ((key: string) => void) | null = null;
</script>

<nav class="b2s-tabs" aria-label="Tabs">
  {#each tabs as tab (tab.key)}
    <button
      type="button"
      class="b2s-tabs__item"
      class:is-active={tab.key === activeKey}
      on:click={() => onChange?.(tab.key)}
      aria-current={tab.key === activeKey ? "page" : undefined}
    >
      {tab.label}
    </button>
  {/each}
</nav>

