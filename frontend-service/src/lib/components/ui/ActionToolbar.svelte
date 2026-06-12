<script lang="ts">
  export let compact = false;
</script>

<div class={`b2s-action-toolbar ${compact ? 'is-compact' : ''}`}>
  <div class="b2s-action-toolbar__left">
    <slot name="left" />
  </div>

  <div class="b2s-action-toolbar__right">
    <slot name="right" />
  </div>
</div>

<style>
  .b2s-action-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
    padding: 0.7rem 0.85rem;
    border: 1px solid var(--b2s-color-border, #dfe6f1);
    border-radius: var(--b2s-radius-md, 16px);
    background: var(--b2s-color-surface, #ffffff);
  }

  .b2s-action-toolbar.is-compact {
    padding: 0.5rem 0.65rem;
  }

  .b2s-action-toolbar__left,
  .b2s-action-toolbar__right {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    flex-wrap: wrap;
  }

  .b2s-action-toolbar__right {
    margin-left: auto;
  }
</style>

