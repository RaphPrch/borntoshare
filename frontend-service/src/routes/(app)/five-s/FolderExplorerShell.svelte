<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import { t } from '$lib/i18n';
  import ParkTree from './explore/ParkTree.svelte';
  import { loadPark, park } from './explore/explore-state.svelte';

  /**
   * The tree of the measured folders on the left, the page on the right: the explorer and the tabs of a folder
   * (duplicates, rights to review) keep the same list of folders in view.
   */
  let { children }: { children: Snippet } = $props();

  onMount(() => {
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
