<script lang="ts">
  export let title = '';
  export let headClass = '';
  export let bodyClass = '';
  export let panelClass = '';
</script>

<article class={`b2s-panel ${panelClass}`.trim()}>
  <div class={`b2s-panel__head ${headClass}`.trim()}>
    <h2>{title}</h2>
    <slot name="actions" />
  </div>

  <div class={bodyClass}>
    <slot />
  </div>
</article>
