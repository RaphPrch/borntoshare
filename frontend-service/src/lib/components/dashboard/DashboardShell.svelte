<script lang="ts">
  export let title: string;
  export let subtitle: string | null = null;
</script>

<div class="b2s-dashboard">
  <header class="b2s-dashboard__header">
    <div>
      <h1>{title}</h1>
      {#if subtitle}
        <p class="b2s-dashboard__subtitle">{subtitle}</p>
      {/if}
    </div>
    <slot name="actions" />
  </header>

  <div class="b2s-dashboard__content">
    <slot />
  </div>
</div>

<style>
  .b2s-dashboard { padding: 18px 18px 24px; }
  .b2s-dashboard__header{
    display:flex; align-items:flex-end; justify-content:space-between;
    gap: 12px; margin-bottom: 14px;
  }
  h1{ margin:0; font-size: 1.35rem; }
  .b2s-dashboard__subtitle{ margin:6px 0 0; color:#64748b; font-size:.95rem; }
  .b2s-dashboard__content{ display:flex; flex-direction:column; gap: 14px; }
</style>
