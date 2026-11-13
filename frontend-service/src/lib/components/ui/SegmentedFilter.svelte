<script lang="ts">
  /**
   * One choice among a few (Tous · Gérés · Injoignables…), the same look on every page.
   * value is bound; a count after the label is optional.
   */
  type Option = { key: string; label: string; count?: number | null };
  interface Props {
    options?: Option[];
    value: string;
    ariaLabel?: string | null;
    onChange?: (key: string) => void;
  }

  let {
    options = [],
    value = $bindable(),
    ariaLabel = null,
    onChange = () => {}
  }: Props = $props();

  function pick(key: string) {
    value = key;
    onChange(key);
  }
</script>

<div class="seg" role="group" aria-label={ariaLabel}>
  {#each options as option (option.key)}
    <button type="button" class:on={value === option.key} aria-pressed={value === option.key} onclick={() => pick(option.key)}>
      {option.label}{#if option.count != null}<span>{option.count}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .seg { display: flex; flex: none; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .seg button { display: inline-flex; align-items: center; gap: 5px; padding: 4px 9px; border: 0; border-radius: var(--b2s-radius-sm); background: transparent; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); white-space: nowrap; cursor: pointer; }
  .seg button:hover { color: var(--b2s-color-text); }
  .seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .seg span { opacity: 0.7; font-weight: 500; }
</style>
