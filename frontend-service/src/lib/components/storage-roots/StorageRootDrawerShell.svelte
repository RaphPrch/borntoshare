<script lang="ts">
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';

  interface Props {
    open?: boolean;
    title?: any;
    subtitle?: string | null;
    onClose?: () => void;
    ariaLabelledby?: string;
    size?: 'md' | 'lg';
    iconClass?: string | null;
    rootClass?: string;
    bodyClass?: string;
    footerClass?: string;
    showFooter?: boolean;
    children?: import('svelte').Snippet;
    footer?: import('svelte').Snippet;
  }

  let {
    open = false,
    title = t('Details'),
    subtitle = null,
    onClose = () => {},
    ariaLabelledby = 'storage-root-drawer-title',
    size = 'md',
    iconClass = null,
    rootClass = '',
    bodyClass = '',
    footerClass = '',
    showFooter = true,
    children,
    footer
  }: Props = $props();

  const footer_render = $derived(footer);
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
  {@render children?.()}

  {#snippet footer()}
  
      {@render footer_render?.()}
    
  {/snippet}
</Drawer>
