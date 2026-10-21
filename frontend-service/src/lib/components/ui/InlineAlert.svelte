<script context="module" lang="ts">
  export type InlineAlertTone = 'info' | 'warning' | 'error' | 'success';
</script>

<script lang="ts">
  export let tone: InlineAlertTone = 'info';
  export let title: string | null = null;
  export let icon: string | null = null;
  export let compact = false;
  let className = '';
  export { className as class };

  const ICONS: Record<InlineAlertTone, string> = {
    info: 'bi-info-circle',
    warning: 'bi-exclamation-triangle',
    error: 'bi-exclamation-octagon',
    success: 'bi-check-circle'
  };

  $: role = tone === 'error' || tone === 'warning' ? 'alert' : 'status';
</script>

<div class={`b2s-inline-alert is-${tone} ${className}`} class:is-compact={compact} {role}>
  <i class={`bi ${icon ?? ICONS[tone]} b2s-inline-alert__icon`} aria-hidden="true"></i>
  <div class="b2s-inline-alert__body">
    {#if title}<div class="b2s-inline-alert__title">{title}</div>{/if}
    <div class="b2s-inline-alert__text"><slot /></div>
  </div>
  {#if $$slots.actions}
    <div class="b2s-inline-alert__actions"><slot name="actions" /></div>
  {/if}
</div>
