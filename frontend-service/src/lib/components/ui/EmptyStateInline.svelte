<script lang="ts">
  export let message: string;
  export let className = '';
</script>

<div class={`b2s-empty-inline ${className}`.trim()}>{message}</div>

<style>
  .b2s-empty-inline {
    color: #64748b;
    padding: 10px 2px;
    font-size: 0.9rem;
  }
</style>
