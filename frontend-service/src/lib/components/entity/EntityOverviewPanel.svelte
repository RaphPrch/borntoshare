<script lang="ts">
  export let title = '';
  export let headClass = '';
  export let bodyClass = '';
  export let panelClass = '';
</script>

<article class={`sed-panel ${panelClass}`.trim()}>
  <div class={`sed-panel__head ${headClass}`.trim()}>
    <h3>{title}</h3>
    <slot name="actions" />
  </div>

  <div class={bodyClass}>
    <slot />
  </div>
</article>

