<script lang="ts">
  /** Inspector of an entity, without a card: one EntityProperty per row. */
  export let title = '';
</script>

<aside class="epr" aria-label={title}>
  <h2>{title}</h2>
  <dl><slot /></dl>
</aside>

<style>
  .epr {
    flex: 1 1 280px;
    max-width: 360px;
  }

  h2 {
    margin: 0 0 4px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  dl {
    margin: 0;
  }
</style>
