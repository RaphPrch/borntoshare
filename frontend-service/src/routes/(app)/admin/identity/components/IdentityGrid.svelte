
<script lang="ts">
  import IdentityCard from './IdentityCard.svelte';
  export let identities: any[] = [];
  export let query = "";
  export let role = "";
  export let source = "";
  export let view: 'grid' | 'table' = 'grid';
  export let onEdit: ((item: any) => void) | null = null;

  const normalize = (value: string) => value?.toLowerCase?.() ?? "";

  $: filtered = identities.filter((item) => {
    const name = normalize(item?.display_name ?? "");
    const mail = normalize(item?.email ?? "");
    const src = normalize(item?.source ?? "");
    const r = normalize(item?.role ?? "");
    const q = normalize(query);

    const matchesQuery = !q || name.includes(q) || mail.includes(q) || src.includes(q);
    const matchesRole = !role || r === normalize(role);
    const matchesSource = !source || src === normalize(source);
    return matchesQuery && matchesRole && matchesSource;
  });
</script>

{#if filtered.length === 0}
  <div class="empty-state">
    <h3>No identities found</h3>
    <p>Create a local user or import an AD group to get started.</p>
  </div>
{:else if view === 'table'}
  <div class="identity-table-card">
    <table class="identity-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>Name</th>
          <th>Source</th>
          <th>Role</th>
          <th>Status</th>
          <th>Email</th>
        </tr>
      </thead>
      <tbody>
        {#each filtered as identity}
          <tr>
            <td>{identity.type}</td>
            <td>{identity.display_name}</td>
            <td>{identity.source}</td>
            <td>{identity.role}</td>
            <td>{identity.status}</td>
            <td>{identity.email ?? '-'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <div class="grid">
    {#each filtered as identity}
      <IdentityCard {identity} {onEdit} />
    {/each}
  </div>
{/if}
