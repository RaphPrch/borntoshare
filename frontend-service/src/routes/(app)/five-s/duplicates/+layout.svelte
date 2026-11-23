<script lang="ts">
  import type { Snippet } from 'svelte';
  import FolderExplorerShell from '../FolderExplorerShell.svelte';

  let { children }: { children: Snippet } = $props();
</script>

<FolderExplorerShell>{@render children()}</FolderExplorerShell>
