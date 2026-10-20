<script lang="ts">
  /** Loading indicator: spinner + message. `block` centres it in a padded area (panels, drawers). */
  export let block = false;
</script>

<div class="b2s-loading" class:is-block={block} role="status" aria-live="polite">
  <span class="b2s-spinner" aria-hidden="true"></span>
  <span><slot /></span>
</div>
