<script lang="ts">
  /** One row of EntityProperties; `chips` lays the value out as a wrapping row. */
  export let label = '';
  export let chips = false;
  export let mono = false;
</script>

<div class="epv">
  <dt>{label}</dt>
  <dd class:is-chips={chips} class:is-mono={mono}><slot /></dd>
</div>

<style>
  .epv {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 0;
    border-bottom: 1px solid var(--b2s-color-border-soft);
    font-size: var(--b2s-fs-sm);
  }

  .epv:last-child {
    border-bottom: 0;
  }

  dt {
    flex: 0 0 96px;
    color: var(--b2s-color-text-muted);
    font-weight: 400;
  }

  dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
  }

  dd.is-chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  dd.is-mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }
</style>
