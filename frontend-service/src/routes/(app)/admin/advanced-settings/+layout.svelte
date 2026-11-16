<script lang="ts">
  import { t } from '$lib/i18n';
  import { page } from '$app/stores';
  import AdvancedSidebar, { type NavItem } from '$lib/components/settings/AdvancedSidebar.svelte';
  interface Props {
    children?: import('svelte').Snippet;
  }

  let { children }: Props = $props();


  // Four groups: what the governance applies, security, the platform, and what connects BornToShare to the rest
  const nav: NavItem[] = [
    { key: 'naming-policies', label: t('Naming policy'), icon: 'bi-input-cursor-text', group: t('General') },
    { key: 'governance', label: t('Governance'), icon: 'bi-shield-check' },
    { key: 'user-sessions', label: t('User sessions'), icon: 'bi-person-lines-fill', group: t('Security') },
    { key: 'logging', label: t('Logging'), icon: 'bi-journal-text' },
    { key: 'network', label: t('Network and DNS'), icon: 'bi-diagram-2', group: t('Network and infrastructure') },
    { key: 'infrastructure', label: t('Infrastructure'), icon: 'bi-hdd-network' },
    { key: 'infrastructure', query: 'tab=workers', label: t('Workers'), icon: 'bi-cpu' },
    { key: 'features', label: t('License and modules'), icon: 'bi-key', group: t('Integrations and license') },
    { key: 'notifications', label: t('Notifications'), icon: 'bi-envelope' },
    { key: 'extensions', label: t('Extensions'), icon: 'bi-plug' }
  ];

  const defaultHeader = {
    title: 'Settings',
    subtitle: t('How BornToShare applies the governance, protects itself and connects to the rest of the company.')
  };

  const headersBySection: Record<string, { title: string; subtitle: string }> = {
    features: {
      title: t('License and modules'),
      subtitle: t('Optional modules opened by a license key, switched on or off.')
    },
    infrastructure: {
      title: t('Infrastructure'),
      subtitle: t('State of the platform, database, workers, health check and data sync.')
    },
    extensions: {
      title: t('Extensions'),
      subtitle: t('Send the events of BornToShare to the tools of the company, and let the supervision check it.')
    }
  };

  let current = $derived($page.url.pathname.split('/').pop() ?? 'naming-policies');
  let header = $derived(headersBySection[current] ?? defaultHeader);
</script>

<div class="b2s-adv">
  <div class="v2-head">
    <div><h1>{header.title}</h1>{#if header.subtitle}<p>{header.subtitle}</p>{/if}</div>
  </div>

  <div class="b2s-adv-grid">
    <AdvancedSidebar {current} items={nav} />
    <main class="b2s-adv-main">
      {@render children?.()}
    </main>
  </div>
</div>
