<script lang="ts">
  import type { ZoneProvisioningPolicy } from "$lib/api/zones";
  import ProvisioningPolicyScreen from "$lib/components/provisioning/ProvisioningPolicyScreen.svelte";
  import { buildZoneProvisioningViewModel } from "$lib/components/provisioning/provisioning-policy.adapter";
  import type { ProvisioningPolicyViewModel } from "$lib/components/provisioning/provisioning-policy.types";

  export let policy: ZoneProvisioningPolicy;
  export let namingTemplateLabel = '';
  export let saving = false;
  export let error: string | null = null;
  export let isDirty = false;
  export let canSave = true;
  export let inheritanceOverview: Record<string, unknown> | null = null;

  export let onChange: ((next: ZoneProvisioningPolicy) => void) | null = null;
  export let onSave: (() => void) | null = null;

  let viewModel: ProvisioningPolicyViewModel = buildZoneProvisioningViewModel(policy);

  $: viewModel = buildZoneProvisioningViewModel(policy);

  $: viewModel = {
    ...viewModel,
    configuration: {
      ...viewModel.configuration,
      onChangeOrganizationalUnit: (value: string) => {
        onChange?.({ ...policy, ou_strategy: "identity_default", base_ou_dn: value, static_ou_dn: null });
      },
      onSavePolicy: onSave ?? undefined,
      savePolicyBusy: saving,
      savePolicyDisabled: !canSave,
      savePolicyLabel: "Save policy"
    }
  };

</script>

<ProvisioningPolicyScreen
  scope="zone"
  title=""
  showPreview={false}
  showEffectiveSave={false}
  showEffectivePreview={false}
  configuration={{
    ...viewModel.configuration,
    namingTemplate: String(namingTemplateLabel || '').trim() || viewModel.configuration.namingTemplate
  }}
  preview={viewModel.preview}
  effective={{
    ...viewModel.effective,
    effectiveNaming: String(namingTemplateLabel || '').trim() || viewModel.effective.effectiveNaming
  }}
  saveDisabled={!canSave}
  saveBusy={saving}
  errorMessage={error}
  showUnsaved={isDirty}
/>

<style>
  .zone-inheritance-overview {
    margin-top: 18px;
    border: 1px solid #dce5f2;
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 12px 28px rgba(15, 31, 61, 0.05);
    overflow: hidden;
  }

  .zone-inheritance-overview__head {
    padding: 16px 18px;
    border-bottom: 1px solid #e5ecf6;
  }

  .zone-inheritance-overview__head h2 {
    margin: 0;
    color: #102243;
    font-size: 16px;
    font-weight: 760;
  }

  .zone-inheritance-overview__head p {
    margin: 4px 0 0;
    color: #607087;
    font-size: 13px;
    font-weight: 600;
  }

  .zone-inheritance-overview__grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .zone-inheritance-overview article {
    min-width: 0;
    padding: 14px 16px;
    border-right: 1px solid #e8eef7;
    border-bottom: 1px solid #e8eef7;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }

  .zone-inheritance-overview article:nth-child(3n) {
    border-right: 0;
  }

  .zone-inheritance-overview article > span {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    background: #eef5ff;
    color: #0a5de8;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .zone-inheritance-overview article.has-warning > span {
    background: #fff5e8;
    color: #a65300;
  }

  .zone-inheritance-overview article div {
    min-width: 0;
    display: grid;
    gap: 3px;
  }

  .zone-inheritance-overview small {
    color: #607087;
    font-size: 12px;
    font-weight: 700;
  }

  .zone-inheritance-overview strong {
    overflow: hidden;
    color: #102243;
    font-size: 14px;
    font-weight: 760;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 900px) {
    .zone-inheritance-overview__grid {
      grid-template-columns: 1fr;
    }

    .zone-inheritance-overview article,
    .zone-inheritance-overview article:nth-child(3n) {
      border-right: 0;
    }
  }
</style>
