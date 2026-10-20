<script lang="ts">
  export let label: string;
  export let help: string | undefined = undefined;
</script>

<div class="adv-field adv-row">
  <span class="adv-field-label">{label}</span>
  <slot />
  {#if help}<p class="help">{help}</p>{/if}
</div>
