<script lang="ts">
  import Drawer from '$lib/components/ui/Drawer.svelte';

  export let open = false;
  export let title = 'Details';
  export let subtitle: string | null = null;
  export let onClose: () => void = () => {};
  export let ariaLabelledby = 'storage-root-drawer-title';
  export let width = '560px';
  export let topOffset = '70px';
  export let rootClass = '';
  export let bodyClass = '';
  export let footerClass = '';
  export let showFooter = true;
</script>

<Drawer
  {open}
  {title}
  {subtitle}
  {onClose}
  {ariaLabelledby}
  {width}
  {topOffset}
  {rootClass}
  {bodyClass}
  {footerClass}
  {showFooter}
>
  <slot />

  <svelte:fragment slot="footer">
    <slot name="footer" />
  </svelte:fragment>
</Drawer>
