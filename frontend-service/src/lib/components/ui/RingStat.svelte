<script lang="ts">
  /**
   * Circular KPI: a part of a whole (coverage, progress, score), drawn in SVG with the colours of the theme. The
   * single ring of the application (5S score and pillars, folder permissions, Dashboard coverage, topology, reviews).
   * value: 0–100, or null when the whole is not known (an empty ring, never « 0 % »). The centre is the children, or
   * the rounded value followed by « % ».
   */
  import type { Snippet } from 'svelte';
  import { ringDash, type RingTone } from '$lib/utils/ring';

  interface Props {
    value: number | null | undefined;
    size?: number;
    /** Thickness of the ring, in px (about a tenth of the size by default) */
    stroke?: number;
    tone?: RingTone;
    label?: string | null;
    /** false: the ring alone (a small one in a list row) */
    center?: boolean;
    children?: Snippet;
  }

  let { value, size = 64, stroke, tone = 'accent', label = null, center = true, children }: Props = $props();
  let width = $derived(stroke ?? Math.max(4, Math.round(size / 10)));
  let r = $derived((size - width) / 2);
</script>

<span class={`ring is-${value == null ? 'idle' : tone}`} style={`width:${size}px;height:${size}px`} role={label ? 'img' : undefined} aria-label={label ?? undefined} aria-hidden={label ? undefined : 'true'}>
  <svg viewBox={`0 0 ${size} ${size}`}>
    <circle class="ring__track" cx={size / 2} cy={size / 2} {r} fill="none" stroke-width={width} />
    {#if value != null && value > 0}
      <circle class="ring__arc" cx={size / 2} cy={size / 2} {r} fill="none" stroke-width={width} stroke-linecap="round" stroke-dasharray={ringDash(value, r)} />
    {/if}
  </svg>
  {#if center}
    <span class="ring__c" style={`font-size:${Math.max(11, Math.round(size / 5))}px`}>
      {#if children}{@render children()}{:else}{value == null ? '—' : `${Math.round(value)} %`}{/if}
    </span>
  {/if}
</span>

<style>
  .ring { position: relative; display: inline-grid; place-items: center; flex: none; --ring: var(--b2s-accent-vivid); }
  .ring.is-ok { --ring: var(--b2s-color-success); }
  .ring.is-warn { --ring: var(--b2s-color-warning); }
  .ring.is-bad { --ring: var(--b2s-color-danger); }
  .ring.is-idle { --ring: var(--b2s-color-border-mid); }
  .ring svg { position: absolute; inset: 0; width: 100%; height: 100%; transform: rotate(-90deg); }
  .ring__track { stroke: var(--b2s-color-neutral-soft); }
  .ring__arc { stroke: var(--ring); transition: stroke-dasharray 0.8s var(--b2s-ease-out); }
  .ring__c { position: relative; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; }
</style>
