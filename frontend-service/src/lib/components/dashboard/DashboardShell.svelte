<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  interface Props {
    title: string;
    subtitle?: string | null;
    actions?: import('svelte').Snippet;
    children?: import('svelte').Snippet;
  }

  let {
    title,
    subtitle = null,
    actions,
    children
  }: Props = $props();
  // « Welcome, First Last »: the display name of the person (a directory account carries first and last name)
  let person = $derived(String(($page.data as any)?.me?.display_name || ($page.data as any)?.user?.display_name || ($page.data as any)?.me?.username || '').trim());
  let heading = $derived(person ? t('Welcome, {name}', { name: person }) : title);
  let under = $derived(person ? [title, subtitle].filter(Boolean).join(' · ') : subtitle);

  const actions_render = $derived(actions);
</script>

<div class="b2s-dashboard">
  <PageHeader title={heading} subtitle={under}>
    {#snippet actions()}
      
        {@render actions_render?.()}
      
      {/snippet}
  </PageHeader>

  <div class="b2s-dashboard__content">
    {@render children?.()}
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
