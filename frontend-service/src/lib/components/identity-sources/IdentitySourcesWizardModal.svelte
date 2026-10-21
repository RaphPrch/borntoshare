<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IdentitySourcesWizard from '$lib/components/identity-sources/IdentitySourcesWizard.svelte';
  import type { IdentitySourcePayload } from '$lib/api/identity-sources';
  import type { IdentitySourceCreateResult } from '$lib/utils/identity-sources';

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

<!-- Mounted only while open so each opening starts from a clean state -->
{#if open}
  <IdentitySourcesWizard open {onClose} {onTest} {onCreate} {existingNames} on:done={() => { handleDone(); onClose(); }} />
{/if}
