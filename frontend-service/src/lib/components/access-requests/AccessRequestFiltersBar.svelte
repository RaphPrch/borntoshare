<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let queryText = '';
  export let onlyMineToAction = false;

  const dispatch = createEventDispatcher<{
    search: { value: string };
    filtersChanged: {
      onlyMineToAction: boolean;
    };
    reset: void;
  }>();
</script>

<div class="filters">
  <label class="search-input">
    <i class="bi bi-search"></i>
    <input
      type="text"
      placeholder="Search by request code or requester"
      value={queryText}
      on:input={(e) => dispatch('search', { value: (e.target as HTMLInputElement).value })}
    />
  </label>

  <label class="checkbox">
    <input
      type="checkbox"
      bind:checked={onlyMineToAction}
      on:change={() => dispatch('filtersChanged', { onlyMineToAction })}
    />
    Only requests requiring my action
  </label>

  {#if queryText || onlyMineToAction}
    <button class="ghost" type="button" on:click={() => dispatch('reset')}>Reset</button>
  {/if}
</div>
