<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  export let title: string;
  export let subtitle: string | null = null;
  // « Welcome, First Last »: the display name of the person (a directory account carries first and last name)
  $: person = String(($page.data as any)?.me?.display_name || ($page.data as any)?.user?.display_name || ($page.data as any)?.me?.username || '').trim();
  $: heading = person ? t('Welcome, {name}', { name: person }) : title;
  $: under = person ? [title, subtitle].filter(Boolean).join(' · ') : subtitle;
</script>

<div class="b2s-dashboard">
  <PageHeader title={heading} subtitle={under}>
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
