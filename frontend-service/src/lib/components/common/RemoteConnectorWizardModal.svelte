<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import WizardModalShell from '$lib/components/common/WizardModalShell.svelte';

  export let open = false;
  export let onClose: () => void;

  export let ariaLabelledby = 'remote-connector-wizard-title';

  export let backdropClass = 'b2s-modal-backdrop b2s-wizard-backdrop is-wizard-backdrop';
  export let modalClass = 'b2s-modal b2s-wizard-modal is-wizard-modal';
  export let modalSize: 'default' | 'wide' = 'default';

  export let WizardComponent: any;
  export let wizardProps: Record<string, any> = {};

  const dispatch = createEventDispatcher<{ done: any }>();

  function handleDone(e: CustomEvent<any>) {
    dispatch('done', e.detail);
  }
</script>

<WizardModalShell
  {open}
  onClose={onClose}
  {ariaLabelledby}
  {backdropClass}
  modalClass={`${modalClass} ${modalSize === 'wide' ? 'b2s-wizard-modal--wide' : ''}`.trim()}
  {WizardComponent}
  {wizardProps}
  on:done={handleDone}
/>
