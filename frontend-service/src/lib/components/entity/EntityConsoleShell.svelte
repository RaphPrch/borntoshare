<!-- Selected entity: header (+ alerts and KPIs), tabs, then the active tab content -->
<section class="b2s-entity-console">
  <slot name="header"></slot>
  <slot name="tabs"></slot>
  <slot></slot>
</section>

<style>
  .b2s-entity-console {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }
</style>
