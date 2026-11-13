<script lang="ts">
  interface Props {
    label: string;
    help?: string | undefined;
    children?: import('svelte').Snippet;
  }

  let { label, help = undefined, children }: Props = $props();
</script>

<div class="adv-field adv-row">
  <span class="adv-field-label">{label}</span>
  {@render children?.()}
  {#if help}<p class="help">{help}</p>{/if}
</div>
