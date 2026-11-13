<script lang="ts">
  import AdminDashboard from '$lib/components/dashboard/AdminDashboard.svelte';
  import UserDashboard from '$lib/components/dashboard/UserDashboard.svelte';

  interface Props {
    data: {
    mode: 'admin' | 'user';
    payload: any;
  };
  }

  let { data }: Props = $props();
</script>

{#if data.mode === 'admin'}
  <AdminDashboard data={data.payload} />
{:else}
  <UserDashboard data={data.payload} />
{/if}
