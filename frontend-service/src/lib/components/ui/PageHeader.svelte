<script lang="ts">
  export let title = '';
  export let subtitle: string | null = null;
</script>

<header class="b2s-page-header">
  <div class="b2s-page-header__main">
    <div class="b2s-page-header__text">
      <h1>{title}</h1>
      {#if subtitle}
        <p>{subtitle}</p>
      {/if}
    </div>
    <div class="b2s-page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</header>

<style>
  .b2s-page-header {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .b2s-page-header__main {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    width: 100%;
  }

  .b2s-page-header__text h1 {
    margin: 0;
    font-size: var(--b2s-fs-page-title);
    line-height: 1.2;
    color: var(--b2s-color-text, var(--b2s-color-text));
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .b2s-page-header__text p {
    margin: 6px 0 0;
    color: var(--b2s-color-text-muted, var(--b2s-color-text-muted));
    font-size: var(--b2s-fs-md);
  }

  .b2s-page-header__actions {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-left: auto;
    color: var(--b2s-color-text-muted, var(--b2s-color-text-muted));
    font-size: var(--b2s-fs-sm);
  }
</style>
