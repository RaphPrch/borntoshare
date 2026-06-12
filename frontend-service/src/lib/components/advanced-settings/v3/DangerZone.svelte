<script lang="ts">
  import AdvCard from './AdvCard.svelte';
  export let title: string = 'Danger Zone';
  export let subtitle: string | undefined = 'Permanent and non-reversible actions.';
  export let icon: string = 'bi-exclamation-triangle';
</script>

<AdvCard {title} {subtitle} {icon} tone="danger">
  <slot />
</AdvCard>
