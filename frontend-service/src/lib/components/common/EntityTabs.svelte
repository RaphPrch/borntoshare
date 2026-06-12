<script lang="ts">
  export type EntityTabItem<Key extends string = string> = {
    key: Key;
    label: string;
    icon?: string | null;
  };

  export let tabs: EntityTabItem[] = [];
  export let activeKey = '';
  export let onChange: ((key: string) => void) | null = null;
  export let ariaLabel = 'Entity sections';
</script>

<nav class="sr-clean-tabs" aria-label={ariaLabel}>
  {#each tabs as tab (tab.key)}
    <button
      type="button"
      class:active={tab.key === activeKey}
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
