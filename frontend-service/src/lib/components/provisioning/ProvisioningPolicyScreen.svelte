<script lang="ts">
  import './provisioning-policy.css';
  import ProvisioningPolicyConfigurationCard from './ProvisioningPolicyConfigurationCard.svelte';
  import ProvisioningPreviewCard from './ProvisioningPreviewCard.svelte';
  import EffectiveConfigurationPreviewCard from './EffectiveConfigurationPreviewCard.svelte';
  import type { ProvisioningPolicyScreenProps } from './provisioning-policy.types';

  export let scope: ProvisioningPolicyScreenProps['scope'];
  export let title: ProvisioningPolicyScreenProps['title'] = '';
  export let saveLabel: ProvisioningPolicyScreenProps['saveLabel'] = 'Save changes';
  export let configuration: ProvisioningPolicyScreenProps['configuration'];
  export let preview: ProvisioningPolicyScreenProps['preview'];
  export let effective: ProvisioningPolicyScreenProps['effective'];
  export let showPreview = true;
  export let onSave: ProvisioningPolicyScreenProps['onSave'];
  export let saveDisabled: ProvisioningPolicyScreenProps['saveDisabled'] = false;
  export let saveBusy: ProvisioningPolicyScreenProps['saveBusy'] = false;
  export let errorMessage: ProvisioningPolicyScreenProps['errorMessage'] = null;
  export let showUnsaved: ProvisioningPolicyScreenProps['showUnsaved'] = false;
  export let showEffectiveSave: ProvisioningPolicyScreenProps['showEffectiveSave'] = true;
  export let showEffectivePreview: ProvisioningPolicyScreenProps['showEffectivePreview'] = true;

  $: effectiveSaveDisabled = Boolean(saveDisabled) || !onSave;
</script>

<section class="provisioning-policy-screen" data-scope={scope}>
  {#if title}
    <h1 class="provisioning-policy-screen__title">{title}</h1>
  {/if}

  <div class="provisioning-policy-grid" class:has-side={showEffectivePreview || errorMessage || showUnsaved}>
    <div class="provisioning-policy-main">
      <ProvisioningPolicyConfigurationCard model={configuration} />
      {#if showPreview}
        <ProvisioningPreviewCard model={preview} />
      {/if}
    </div>

    {#if showEffectivePreview || errorMessage || showUnsaved}
      <aside class="provisioning-policy-side">
        {#if showEffectivePreview}
          <EffectiveConfigurationPreviewCard
            model={effective}
            saveLabel={saveLabel}
            onSave={onSave}
            saveDisabled={effectiveSaveDisabled}
            saveBusy={saveBusy}
            showSaveAction={showEffectiveSave}
          />
        {/if}

        {#if errorMessage}
          <div class="provisioning-error" aria-live="polite">{errorMessage}</div>
        {/if}

        {#if showUnsaved}
          <div class="provisioning-field__help" aria-live="polite">Unsaved changes</div>
        {/if}
      </aside>
    {/if}
  </div>
</section>
