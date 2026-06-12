<script lang="ts">
  import {
    resolveStatusVariant,
    type StatusVariant,
  } from '$lib/constants/status';

  export let status: string | null | undefined = 'running';
  export let label: string | null = null;
  export let compact = false;
  export let showDot = true;
  export let variant: StatusVariant | null = null;

  const toBadgeLabel = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return 'Unknown';
    return raw.replace(/[_-]+/g, ' ');
  };

  $: computedLabel = label ?? toBadgeLabel(status);
  $: resolvedVariant = variant ?? resolveStatusVariant(status);
  $: cls = `is-${resolvedVariant}`;
</script>

<span class={`b2s-status ${cls} ${compact ? 'is-compact' : ''}`}>
  {#if showDot}
    <span class="b2s-status__dot" aria-hidden="true"></span>
  {/if}
  {computedLabel}
</span>
