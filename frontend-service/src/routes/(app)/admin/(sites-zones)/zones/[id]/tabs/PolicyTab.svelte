<script lang="ts">
  import { t } from '$lib/i18n';
  import type { ZoneProvisioningPolicy } from "$lib/api/zones";
  import ProvisioningPolicyScreen from "$lib/components/provisioning/ProvisioningPolicyScreen.svelte";
  import { buildZoneProvisioningViewModel } from "$lib/components/provisioning/provisioning-policy.adapter";
  import type { ProvisioningPolicyViewModel } from "$lib/components/provisioning/provisioning-policy.types";

  export let policy: ZoneProvisioningPolicy;
  export let zoneId: number | null = null;
  export let namingTemplateLabel = '';
  export let saving = false;
  export let error: string | null = null;
  export let isDirty = false;
  export let canSave = true;
  export let inheritanceOverview: Record<string, unknown> | null = null;

  export let onChange: ((next: ZoneProvisioningPolicy) => void) | null = null;
  export let onSave: (() => void) | null = null;
  export let onChangeNamingTemplate: ((value: string) => void) | null = null;

  let viewModel: ProvisioningPolicyViewModel = buildZoneProvisioningViewModel(policy);

  $: viewModel = buildZoneProvisioningViewModel(policy);

  $: viewModel = {
    ...viewModel,
    configuration: {
      ...viewModel.configuration,
      onChangeOrganizationalUnit: (value: string) => {
        onChange?.({ ...policy, ou_strategy: "identity_default", base_ou_dn: value, static_ou_dn: null });
      },
      onChangeNamingTemplate: onChangeNamingTemplate ?? undefined,
      onSavePolicy: onSave ?? undefined,
      savePolicyBusy: saving,
      savePolicyDisabled: !canSave,
      savePolicyLabel: t('Save policy')
    }
  };

</script>

<ProvisioningPolicyScreen
  scope="zone"
  saveLabel={t('Save policy')}
  configuration={{
    ...viewModel.configuration,
    namingTemplate: String(namingTemplateLabel || '').trim() || viewModel.configuration.namingTemplate
  }}
  effective={{
    ...viewModel.effective,
    effectiveNaming: String(namingTemplateLabel || '').trim() || viewModel.effective.effectiveNaming
  }}
  previewTarget={{ zone_id: zoneId ?? (Number(policy?.zone_id ?? 0) || null) }}
  saveDisabled={!canSave}
  saveBusy={saving}
  errorMessage={error}
  showUnsaved={isDirty}
/>

