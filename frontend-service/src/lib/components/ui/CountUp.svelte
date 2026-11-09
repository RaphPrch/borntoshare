<script lang="ts">
  import { tweened } from 'svelte/motion';
  import { cubicOut } from 'svelte/easing';
  import { dur } from '$lib/utils/motion';

  /**
   * A figure that counts to its value: from 0 when it first appears, from its previous value when it changes
   * (a scan that finds more files, a quota read again). Instant when the person asked for less motion.
   */
  export let value: number | null | undefined;
  export let format: (value: number) => string = (n) => Math.round(n).toLocaleString('fr-FR');
  export let empty = '—';
  export let duration = 600;

  const shown = tweened(0, { duration: 0 });
  $: if (value != null && Number.isFinite(Number(value))) shown.set(Number(value), { duration: dur(duration), easing: cubicOut });
</script>

{#if value == null || !Number.isFinite(Number(value))}{empty}{:else}<span class="b2s-countup">{format($shown)}</span>{/if}

<style>
  .b2s-countup { font-variant-numeric: tabular-nums; }
</style>
