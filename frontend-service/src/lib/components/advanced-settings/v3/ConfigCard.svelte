<script lang="ts">
  import AdvCard from './AdvCard.svelte';
  export let title: string;
  export let subtitle: string | undefined = undefined;
  export let icon: string | undefined = undefined;
</script>

<AdvCard {title} {subtitle} {icon}>
  <slot />
</AdvCard>
