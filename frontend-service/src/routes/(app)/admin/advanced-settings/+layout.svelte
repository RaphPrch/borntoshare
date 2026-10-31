<script lang="ts">
  import { t } from '$lib/i18n';
  import { page } from '$app/stores';

  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import AdvancedSidebar, { type NavItem } from '$lib/components/settings/AdvancedSidebar.svelte';

  export let data: any;

  const nav: NavItem[] = [
    { key: 'naming-policies', label: t('Naming policy'), icon: 'bi-input-cursor-text' },
    { key: 'governance', label: t('Governance'), icon: 'bi-shield-check' },
    { key: 'logging', label: t('Logging'), icon: 'bi-journal-text' },
    { key: 'user-sessions', label: t('User sessions'), icon: 'bi-person-lines-fill' },
    { key: 'infrastructure', label: t('Infrastructure'), icon: 'bi-hdd-network' }
  ];

  const defaultHeader = {
    title: t('Advanced Settings'),
    subtitle: t('Advanced technical settings.')
  };

  const headersBySection: Record<string, { title: string; subtitle: string }> = {
    infrastructure: {
      title: t('Infrastructure'),
      subtitle: t('State of the platform, database, workers, health check and data sync.')
    }
  };

  $: current = $page.url.pathname.split('/').pop() ?? 'naming-policies';
  $: header = headersBySection[current] ?? defaultHeader;
</script>

<div class="b2s-adv">
  <PageHeader title={header.title} subtitle={header.subtitle} />

  <div class="b2s-adv-grid">
    <AdvancedSidebar {current} items={nav} />
    <main class="b2s-adv-main">
      <slot />
    </main>
  </div>
</div>
