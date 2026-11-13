<script module lang="ts">
  export type InlineAlertTone = 'info' | 'warning' | 'error' | 'success';
</script>

<script lang="ts">
  interface Props {
    tone?: InlineAlertTone;
    title?: string | null;
    icon?: string | null;
    compact?: boolean;
    class?: string;
    children?: import('svelte').Snippet;
    actions?: import('svelte').Snippet;
  }

  let {
    tone = 'info',
    title = null,
    icon = null,
    compact = false,
    class: className = '',
    children,
    actions
  }: Props = $props();
  

  const ICONS: Record<InlineAlertTone, string> = {
    info: 'bi-info-circle',
    warning: 'bi-exclamation-triangle',
    error: 'bi-exclamation-octagon',
    success: 'bi-check-circle'
  };

  let role = $derived(tone === 'error' || tone === 'warning' ? 'alert' : 'status');
</script>

<div class={`b2s-inline-alert is-${tone} ${className}`} class:is-compact={compact} {role}>
  <i class={`bi ${icon ?? ICONS[tone]} b2s-inline-alert__icon`} aria-hidden="true"></i>
  <div class="b2s-inline-alert__body">
    {#if title}<div class="b2s-inline-alert__title">{title}</div>{/if}
    <div class="b2s-inline-alert__text">{@render children?.()}</div>
  </div>
  {#if actions}
    <div class="b2s-inline-alert__actions">{@render actions?.()}</div>
  {/if}
</div>
