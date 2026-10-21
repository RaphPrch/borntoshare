<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';

  export let title: string;
  export let subtitle: string | null = null;
</script>

<div class="b2s-dashboard">
  <PageHeader {title} {subtitle}>
    <svelte:fragment slot="actions">
      <slot name="actions" />
    </svelte:fragment>
  </PageHeader>

  <div class="b2s-dashboard__content">
    <slot />
  </div>
</div>

<style>
  .b2s-dashboard {
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: var(--b2s-page-padding);
  }
  .b2s-dashboard__content { display: flex; flex-direction: column; gap: 14px; }
</style>
