<script lang="ts">
  export let id: string | undefined = undefined;
</script>

<p class="b2s-field-error" {id} role="alert">
  <i class="bi bi-exclamation-circle" aria-hidden="true"></i>
  <span><slot /></span>
</p>
