<script lang="ts">
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import type { EntityAlertStripItem } from '$lib/components/entity/entity-alerts.types';

  interface Props {
    open?: boolean;
    title?: any;
    subtitle?: string | null;
    items?: EntityAlertStripItem[];
    emptyLabel?: any;
    onClose?: () => void;
    ariaLabelledby?: string;
    size?: 'md' | 'lg';
  }

  let {
    open = false,
    title = t('Alerts'),
    subtitle = null,
    items = [],
    emptyLabel = t('No alert found.'),
    onClose = () => {},
    ariaLabelledby = 'entity-alerts-drawer-title',
    size = 'md'
  }: Props = $props();
</script>

<Drawer
  iconClass="bi bi-exclamation-triangle"
  {open}
  {title}
  {subtitle}
  {onClose}
  {ariaLabelledby}
  {size}
  showFooter={false}
>
  {#if items.length === 0}
    <div class="sr-loading-state empty">{emptyLabel}</div>
  {:else}
    <div class="sr-alerts-drawer-list">
      {#each items as alert (alert.key)}
        <article class={`sr-alerts-drawer-row is-${alert.tone ?? 'warning'}`}>
          <span class="sr-alerts-drawer-row__icon">
            <i class={`bi ${alert.tone === 'error' ? 'bi-x-circle-fill' : 'bi-exclamation-triangle-fill'}`} aria-hidden="true"></i>
          </span>
          <div>
            <strong>{alert.title}</strong>
            {#if alert.subtitle}
              <small>{alert.subtitle}</small>
            {/if}
          </div>
        </article>
      {/each}
    </div>
  {/if}
</Drawer>
