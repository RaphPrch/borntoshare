<script lang="ts">

  import { t } from '$lib/i18n';
  import type { ZoneProvisioningPolicy } from "$lib/api/zones";
  import ProvisioningPolicyScreen from "$lib/components/provisioning/ProvisioningPolicyScreen.svelte";
  import { buildZoneProvisioningViewModel } from "$lib/components/provisioning/provisioning-policy.adapter";
  import type { ProvisioningPolicyViewModel } from "$lib/components/provisioning/provisioning-policy.types";


  interface Props {
    policy: ZoneProvisioningPolicy;
    zoneId?: number | null;
    namingTemplateLabel?: string;
    saving?: boolean;
    error?: string | null;
    isDirty?: boolean;
    canSave?: boolean;
    onChange?: ((next: ZoneProvisioningPolicy) => void) | null;
    onSave?: (() => void) | null;
    onDiscard?: (() => void) | null;
    onChangeNamingTemplate?: ((value: string) => void) | null;
  }

  let {
    policy,
    zoneId = null,
    namingTemplateLabel = '',
    saving = false,
    error = null,
    isDirty = false,
    canSave = true,
    onChange = null,
    onSave = null,
    onDiscard = null,
    onChangeNamingTemplate = null
  }: Props = $props();

  let viewModel: ProvisioningPolicyViewModel = $derived.by(() => {
    const base = buildZoneProvisioningViewModel(policy);
    return {
      ...base,
      configuration: {
        ...base.configuration,
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
  });

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
  {onDiscard}
/>

