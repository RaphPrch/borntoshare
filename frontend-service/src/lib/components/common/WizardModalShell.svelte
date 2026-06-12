<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SvelteComponent } from 'svelte';
  import AppModal from '$lib/components/common/AppModal.svelte';

  export let open = false;
  export let onClose: () => void;

  export let ariaLabelledby: string;
  export let backdropClass: string;
  export let modalClass: string;

  export let WizardComponent: typeof SvelteComponent;
  export let wizardProps: Record<string, any> = {};

  const dispatch = createEventDispatcher<{ done: any }>();

  function handleDone(e: CustomEvent<any>) {
    dispatch('done', e.detail);
    onClose();
  }
</script>

<AppModal
  {open}
  onClose={onClose}
  {backdropClass}
  {modalClass}
  {ariaLabelledby}
>
  <svelte:component this={WizardComponent} {...wizardProps} on:done={handleDone} />
</AppModal>
