<script lang="ts">
  import { page } from '$app/stores';

  import SectionHeader from '$lib/components/advanced-settings/v3/SectionHeader.svelte';
  import AdvancedSidebar, { type NavItem } from '$lib/components/advanced-settings/v3/AdvancedSidebar.svelte';

  export let data: any;

  const nav: NavItem[] = [
    { key: 'naming-policies', label: 'Naming policy', icon: 'bi-input-cursor-text' },
    { key: 'security', label: 'Security', icon: 'bi-shield-lock' },
    { key: 'logging', label: 'Logging', icon: 'bi-journal-text' },
    { key: 'user-sessions', label: 'User sessions', icon: 'bi-person-lines-fill' },
    { key: 'maintenance', label: 'Maintenance', icon: 'bi-tools' }
  ];

  const defaultHeader = {
    title: 'Advanced Settings',
    subtitle: 'Advanced technical settings and maintenance operations.'
  };

  const headersBySection: Record<string, { title: string; subtitle: string }> = {};

  $: current = $page.url.pathname.split('/').pop() ?? 'naming-policies';
  $: header = headersBySection[current] ?? defaultHeader;
</script>

<div class="b2s-adv">
  <SectionHeader title={header.title} subtitle={header.subtitle}>
    <div slot="actions">
      <!-- Reserved for future global actions (export config, etc.) -->
    </div>
  </SectionHeader>

  <div class="b2s-adv-grid">
    <AdvancedSidebar {current} items={nav} />
    <main class="b2s-adv-main">
      <slot />
    </main>
  </div>
</div>
