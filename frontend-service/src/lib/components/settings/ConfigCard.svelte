<script lang="ts">
  import AdvCard from './AdvCard.svelte';
  interface Props {
    title: string;
    subtitle?: string | undefined;
    icon?: string | undefined;
    children?: import('svelte').Snippet;
  }

  let {
    title,
    subtitle = undefined,
    icon = undefined,
    children
  }: Props = $props();
</script>

<AdvCard {title} {subtitle} {icon}>
  {@render children?.()}
</AdvCard>
