<script lang="ts">
  export let message: string;
  export let className = '';
</script>

<div class={`b2s-empty-inline ${className}`.trim()}>{message}</div>

<style>
  /* A list or a panel with nothing to show: the same short sentence, centered, everywhere */
  .b2s-empty-inline {
    padding: 20px 12px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-text-sm);
    text-align: center;
  }
</style>
