<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    void goto('/storage-roots?create=1', { replaceState: true });
  });
</script>

<p>Redirecting…</p>
