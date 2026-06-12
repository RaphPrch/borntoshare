
<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import SearchField from '$lib/components/common/SearchField.svelte';

  export let search = "";
  export let role = "";
  export let source = "";

  const dispatch = createEventDispatcher();

  const clearAll = () => {
    search = "";
    role = "";
    source = "";
    dispatch("clear");
  };
</script>

<div class="filters">
  <SearchField
    wrapperClass="filters__search"
    placeholder="Search identities..."
    ariaLabel="Search identities"
    bind:value={search}
  />
  <select bind:value={role}>
    <option value="">All roles</option>
    <option value="admin">Admin</option>
    <option value="user">User</option>
    <option value="group">Group</option>
  </select>
  <select bind:value={source}>
    <option value="">All sources</option>
    <option value="local">Local</option>
    <option value="ad">AD</option>
  </select>
  <button class="filters__clear" type="button" on:click={clearAll}>
    <i class="bi bi-eraser"></i>
    Clear
  </button>
  <button class="filters__filter" type="button">
    <i class="bi bi-funnel"></i>
    Filter
  </button>
</div>
