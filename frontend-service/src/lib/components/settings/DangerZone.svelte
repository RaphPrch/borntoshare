<script lang="ts">
  import AdvCard from './AdvCard.svelte';
  interface Props {
    title?: string;
    subtitle?: string | undefined;
    icon?: string;
    children?: import('svelte').Snippet;
  }

  let {
    title = 'Danger Zone',
    subtitle = 'Permanent and non-reversible actions.',
    icon = 'bi-exclamation-triangle',
    children
  }: Props = $props();
</script>

<AdvCard {title} {subtitle} {icon} tone="danger">
  {@render children?.()}
</AdvCard>
