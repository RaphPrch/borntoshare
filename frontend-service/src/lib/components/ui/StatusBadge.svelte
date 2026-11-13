<script lang="ts">
  import { t } from '$lib/i18n';
  import {
    resolveStatusVariant,
    type StatusVariant,
  } from '$lib/utils/status';

  interface Props {
    status?: string | null | undefined;
    label?: string | null;
    compact?: boolean;
    showDot?: boolean;
    variant?: StatusVariant | null;
  }

  let {
    status = 'running',
    label = null,
    compact = false,
    showDot = true,
    variant = null
  }: Props = $props();

  const toBadgeLabel = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return t('Unknown');
    return raw.replace(/[_-]+/g, ' ');
  };

  let computedLabel = $derived(label ?? toBadgeLabel(status));
  let resolvedVariant = $derived(variant ?? resolveStatusVariant(status));
  let cls = $derived(`is-${resolvedVariant}`);
</script>

<span class={`b2s-status ${cls} ${compact ? 'is-compact' : ''}`}>
  {#if showDot}
    <span class="b2s-status__dot" aria-hidden="true"></span>
  {/if}
  {computedLabel}
</span>
