<script lang="ts">
  export let title: string;
  export let subtitle: string | undefined = undefined;
</script>

<header class="b2s-adv-header">
  <div>
    <h1>{title}</h1>
    {#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
  </div>
  <div class="b2s-adv-header-actions">
    <slot name="actions" />
  </div>
</header>
