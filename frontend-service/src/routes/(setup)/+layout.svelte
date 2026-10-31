<script lang="ts">
  // Same global styles as the public routes: the guided setup has no navigation of its own
  import '@fontsource-variable/geist';
  import '@fontsource-variable/geist-mono';
  import '$lib/styles/tokens.css';
  import '$lib/styles/bootstrap-subset.css';
  import '$lib/styles/bootstrap-icons.min.css';
  import '$lib/styles/modals.css';
  import '$lib/styles/app.css';
  import '$lib/styles/buttons.css';
  import Toaster from '$lib/components/ui/Toaster.svelte';
</script>

<slot />
<Toaster />
