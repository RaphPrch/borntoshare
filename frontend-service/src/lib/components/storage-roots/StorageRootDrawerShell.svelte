<script lang="ts">
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';

  export let open = false;
  export let title = t('Details');
  export let subtitle: string | null = null;
  export let onClose: () => void = () => {};
  export let ariaLabelledby = 'storage-root-drawer-title';
  export let size: 'md' | 'lg' = 'md';
  export let iconClass: string | null = null;
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
  {size}
  {iconClass}
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
