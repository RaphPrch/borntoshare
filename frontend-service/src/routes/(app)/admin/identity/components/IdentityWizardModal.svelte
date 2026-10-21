
<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IdentityWizard from './IdentityWizard.svelte';

  export let open = false;
  export let onClose: () => void;

  const dispatch = createEventDispatcher<{ done: { id?: string | number } }>();
</script>

<!-- Mounted only while open so each opening starts from a clean state -->
{#if open}
  <IdentityWizard
    open
    onCancel={onClose}
    on:done={(event) => {
      dispatch('done', event.detail);
      onClose();
    }}
  />
{/if}
