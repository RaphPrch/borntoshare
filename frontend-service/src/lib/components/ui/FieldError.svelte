<script lang="ts">
  interface Props {
    id?: string | undefined;
    children?: import('svelte').Snippet;
  }

  let { id = undefined, children }: Props = $props();
</script>

<p class="b2s-field-error" {id} role="alert">
  <i class="bi bi-exclamation-circle" aria-hidden="true"></i>
  <span>{@render children?.()}</span>
</p>
