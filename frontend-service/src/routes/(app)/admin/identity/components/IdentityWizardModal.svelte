
<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import WizardModalShell from '$lib/components/common/WizardModalShell.svelte';
  import IdentityWizard from './IdentityWizard.svelte';

  export let open = false;
  export let onClose: () => void;

  const dispatch = createEventDispatcher<{ done: { id?: string | number } }>();
</script>

<WizardModalShell
  {open}
  onClose={onClose}
  ariaLabelledby="identity-wizard-title"
  backdropClass="b2s-modal-backdrop b2s-wizard-backdrop is-wizard-backdrop--clear"
  modalClass="b2s-modal b2s-wizard-modal is-wizard-modal"
  WizardComponent={IdentityWizard}
  wizardProps={{
    open,
    onCancel: onClose
  }}
  on:done={(event) => dispatch('done', event.detail)}
/>
