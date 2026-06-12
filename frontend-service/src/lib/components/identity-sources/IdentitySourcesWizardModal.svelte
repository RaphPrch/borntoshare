<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import RemoteConnectorWizardModal from '$lib/components/common/RemoteConnectorWizardModal.svelte';
  import IdentitySourcesWizard from '$lib/components/identity-sources/IdentitySourcesWizard.svelte';
  import type { IdentitySourcePayload } from '$lib/api/identity-sources';
  import type { IdentitySourceCreateResult } from '$lib/services/identity-sources.helpers';

  export let open = false;
  export let onClose: () => void;
  export let onTest: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<{
    ok: boolean;
    checks: Array<{ key: string; ok: boolean; message?: string }>;
    status?: string;
    job_id?: string | number;
  }>;
  export let onCreate: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<IdentitySourceCreateResult>;
  export let existingNames: string[] = [];

  const dispatch = createEventDispatcher<{ done: void }>();

  function handleDone() {
    dispatch('done');
  }
</script>

<RemoteConnectorWizardModal
  {open}
  onClose={onClose}
  ariaLabelledby="identity-sources-wizard-title"
  backdropClass="b2s-modal-backdrop b2s-wizard-backdrop b2s-identity-source-wizard-backdrop"
  modalClass="b2s-modal b2s-wizard-modal b2s-wizard-modal--identity-source is-wizard-modal"
  WizardComponent={IdentitySourcesWizard}
  wizardProps={{ onTest, onCreate, existingNames }}
  on:done={handleDone}
/>
