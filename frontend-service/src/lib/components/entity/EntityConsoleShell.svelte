<script>
  /**
   * @typedef {Object} Props
   * @property {import('svelte').Snippet} [header]
   * @property {import('svelte').Snippet} [tabs]
   * @property {import('svelte').Snippet} [children]
   */

  /** @type {Props} */
  let { header, tabs, children } = $props();
</script>

<!-- Selected entity: header (+ alerts and KPIs), tabs, then the active tab content -->
<section class="b2s-entity-console">
  {@render header?.()}
  {@render tabs?.()}
  {@render children?.()}
</section>

<style>
  .b2s-entity-console {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }
</style>
