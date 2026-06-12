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
    gap: 1rem;
    flex-wrap: wrap;
  }

  .b2s-page-header__text h1 {
    margin: 0;
    font-size: clamp(1.35rem, 2vw, 1.8rem);
    color: var(--b2s-color-text, #0f172a);
    font-weight: 800;
    letter-spacing: -0.01em;
  }

  .b2s-page-header__text p {
    margin: 0.3rem 0 0;
    color: var(--b2s-color-text-muted, #64748b);
    font-size: 0.94rem;
  }

  .b2s-page-header__actions {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
</style>
