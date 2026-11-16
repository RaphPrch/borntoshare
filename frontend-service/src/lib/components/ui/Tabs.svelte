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

  /** Tabs inside a page: the same underlined tabs as the sections of the menu (v2-tabs), one look everywhere. */
  interface Props {
    tabs?: TabItem[];
    activeKey?: string;
    onChange?: ((key: string) => void) | null;
    ariaLabel?: any;
  }

  let {
    tabs = [],
    activeKey = '',
    onChange = null,
    ariaLabel = t('Sections')
  }: Props = $props();
</script>

<nav class="v2-tabs" aria-label={ariaLabel}>
  {#each tabs as tab (tab.key)}
    <button
      type="button"
      class:is-on={tab.key === activeKey}
      aria-current={tab.key === activeKey ? 'page' : undefined}
      onclick={() => onChange?.(tab.key)}
    >
      {#if tab.icon}<i class={`bi ${tab.icon}`} aria-hidden="true"></i>{/if}
      {tab.label}
      {#if tab.count !== undefined && tab.count !== null}<b>{tab.count}</b>{/if}
    </button>
  {/each}
</nav>
