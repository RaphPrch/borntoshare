<script lang="ts">
  import { page } from '$app/stores';

  import SectionHeader from '$lib/components/settings/SectionHeader.svelte';
  import AdvancedSidebar, { type NavItem } from '$lib/components/settings/AdvancedSidebar.svelte';

  export let data: any;

  const nav: NavItem[] = [
    { key: 'naming-policies', label: 'Naming policy', icon: 'bi-input-cursor-text' },
    { key: 'logging', label: 'Logging', icon: 'bi-journal-text' },
    { key: 'user-sessions', label: 'User sessions', icon: 'bi-person-lines-fill' }
  ];

  const defaultHeader = {
    title: 'Advanced Settings',
    subtitle: 'Advanced technical settings.'
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
