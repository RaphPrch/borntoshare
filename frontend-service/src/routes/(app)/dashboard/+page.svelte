<script lang="ts">
  import AdminDashboard from '$lib/components/dashboard/AdminDashboard.svelte';
  import UserDashboard from '$lib/components/dashboard/UserDashboard.svelte';

  export let data: {
    mode: 'admin' | 'user';
    payload: any;
  };
</script>

{#if data.mode === 'admin'}
  <AdminDashboard data={data.payload} />
{:else}
  <UserDashboard data={data.payload} />
{/if}
