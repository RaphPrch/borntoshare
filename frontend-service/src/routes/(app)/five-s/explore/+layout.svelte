<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import { fivesEnabled } from '$lib/utils/features';
  import { t } from '$lib/i18n';
  import ParkTree from './ParkTree.svelte';
  import { loadPark, park } from './explore-state.svelte';

  /** The explorer: the tree of the measured folders on the left, the page (the table, or a folder's content) on the right. */
  let { children }: { children: Snippet } = $props();

  onMount(() => {
    if (!$fivesEnabled) {
      park.loading = false;
      park.error = t('The 5S module is not active.');
      return;
    }
    void loadPark(fetch, t('Unable to load the 5S.'));
  });
</script>

<div class="xp">
  <ParkTree />
  <div class="xp__main">{@render children()}</div>
</div>

<style>
  .xp { display: grid; grid-template-columns: 280px minmax(0, 1fr); align-items: start; }
  .xp__main { min-width: 0; }
</style>
