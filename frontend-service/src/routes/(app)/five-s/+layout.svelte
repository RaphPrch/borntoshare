<script lang="ts">
  import type { Snippet } from 'svelte';
  import { page } from '$app/stores';
  import FivesOffNotice from '$lib/components/settings/FivesOffNotice.svelte';

  let { children }: { children: Snippet } = $props();

  // Set by +layout.server.ts when the module is not usable: no 5S screen loads then
  let off = $derived(($page.data as { fivesOff?: { reason: string } | null }).fivesOff ?? null);
</script>

{#if off}
  <FivesOffNotice reason={off.reason} />
{:else}
  {@render children()}
{/if}
