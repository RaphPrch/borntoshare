<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';

  /**
   * Page layout shared by zones, storage endpoints and storage roots:
   * page band (title, subtitle, actions), list pane on the left, selected entity on the right.
   * Slots: "actions" (band buttons), "list" (EntitySidebarTree), default (entity detail).
   */
  export let title: string;
  export let subtitle: string | null = null;
</script>

<div class="b2s-workspace-page">
  <PageHeader {title} {subtitle}>
    <svelte:fragment slot="actions"><slot name="actions" /></svelte:fragment>
  </PageHeader>

  <div class="b2s-workspace" class:has-list={$$slots.list}>
    {#if $$slots.list}<slot name="list" />{/if}
    <section class="b2s-workspace__detail">
      <slot />
    </section>
  </div>
</div>

<style>
  .b2s-workspace-page {
    display: grid;
    gap: 20px;
    padding: var(--b2s-page-padding);
  }

  .b2s-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
    align-items: start;
  }

  .b2s-workspace.has-list {
    grid-template-columns: 320px minmax(0, 1fr);
  }

  .b2s-workspace__detail {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }

  @media (max-width: 1100px) {
    .b2s-workspace.has-list {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
