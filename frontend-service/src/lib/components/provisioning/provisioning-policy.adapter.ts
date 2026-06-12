import type { ZoneProvisioningPolicy } from '../../api/zones';
import type { StorageEndpointProvisioningPolicy } from '../../api/storage-endpoints';
import type {
  EffectiveProvisioningModel,
  ProvisioningConfigurationModel,
  ProvisioningPolicyViewModel,
  ProvisioningPreviewModel
} from './provisioning-policy.types';

export type { ProvisioningPolicyViewModel } from './provisioning-policy.types';

const txt = (value: unknown): string => String(value ?? '').trim();

const TOKENS_HINT = 'Available tokens: {PREFIX}, {ROOTCODE}, {PERM}';

function resolvePreviewStatus(status: string): ProvisioningPreviewModel['status'] {
  const key = txt(status).toLowerCase();
  if (key === 'ready' || key === 'success' || key === 'configured') return 'ready';
  if (key === 'warning' || key === 'running' || key === 'checking') return 'warning';
  return 'invalid';
}

function resolveSourceVariant(source: string): EffectiveProvisioningModel['sourceVariant'] {
  const key = txt(source).toLowerCase();
  if (key === 'endpoint') return 'endpoint';
  if (key === 'zone') return 'zone';
  if (key === 'global') return 'global';
  return 'inherited';
}

export function buildZoneProvisioningViewModel(input: unknown): ProvisioningPolicyViewModel {
  const policy = (input ?? {}) as ZoneProvisioningPolicy & {
    zone_name?: string | null;
    naming_template?: string | null;
    effective_preview?: {
      effective_ou_dn?: string | null;
      warnings?: string[];
      example_groups?: {
        based_on_root_code?: string | null;
        read?: string | null;
        write?: string | null;
      } | null;
    } | null;
    example_groups?: {
      based_on_root_code?: string | null;
      read?: string | null;
      write?: string | null;
    } | null;
  };

  const organizationalUnit = txt(policy?.base_ou_dn ?? policy?.static_ou_dn);
  const namingTemplate = txt(policy?.naming_template) || '{PREFIX}-{ROOTCODE}-{PERM}';

  const rootCode =
    txt(policy?.effective_preview?.example_groups?.based_on_root_code) ||
    txt(policy?.example_groups?.based_on_root_code) ||
    'finance_rw';
  const readGroup =
    txt(policy?.effective_preview?.example_groups?.read) || txt(policy?.example_groups?.read) || 'B2S_finance_rw_RX';
  const writeGroup =
    txt(policy?.effective_preview?.example_groups?.write) || txt(policy?.example_groups?.write) || 'B2S_finance_rw_RW';

  const configuration: ProvisioningConfigurationModel = {
    scope: 'zone',
    organizationalUnit,
    namingTemplate,
    tokensHint: TOKENS_HINT,
    canEditOverrideFields: true
  };

  const preview: ProvisioningPreviewModel = {
    status: resolvePreviewStatus(policy?.effective_preview?.warnings?.length ? 'warning' : 'ready'),
    statusLabel: policy?.effective_preview?.warnings?.length ? 'Review before provisioning' : 'Ready to provision',
    rootCode,
    readGroup,
    writeGroup
  };

  const effective: EffectiveProvisioningModel = {
    sourceLabel: 'Zone policy',
    sourceVariant: 'zone',
    effectivePrefix: 'B2S',
    effectiveOu: organizationalUnit || txt(policy?.effective_preview?.effective_ou_dn) || 'Not configured',
    effectiveNaming: namingTemplate,
    rootcodeStrategy: 'BASENAME',
    exampleReadGroup: readGroup,
    exampleWriteGroup: writeGroup
  };

  return {
    scope: 'zone',
    configuration,
    preview,
    effective
  };
}

export function buildStorageEndpointProvisioningViewModel(input: unknown): ProvisioningPolicyViewModel {
  const policy = (input ?? {}) as StorageEndpointProvisioningPolicy;
  const mode: 'inherit' | 'override' = policy?.policy_mode === 'override' ? 'override' : 'inherit';

  const inheritedOu = txt(policy?.inherited_values?.ou_dn);
  const inheritedTemplate = txt(policy?.inherited_values?.naming_template) || '{PREFIX}-{ROOTCODE}-{PERM}';
  const endpointOu = txt(policy?.endpoint_values?.ou_dn);
  const endpointTemplate = txt(policy?.endpoint_values?.naming_template);
  const effectiveNamingPolicy = policy?.effective_naming_policy ?? null;

  const organizationalUnit = mode === 'override' ? endpointOu : inheritedOu;
  const namingTemplate =
    mode === 'override'
      ? endpointTemplate || inheritedTemplate
      : txt(effectiveNamingPolicy?.template) || inheritedTemplate;

  const rootCode = txt(policy?.example_groups?.based_on_root_code) || 'finance_rw';
  const readGroup = txt(policy?.example_groups?.read) || 'B2S_finance_rw_RX';
  const writeGroup = txt(policy?.example_groups?.write) || 'B2S_finance_rw_RW';

  const configuration: ProvisioningConfigurationModel = {
    scope: 'storage-endpoint',
    inheritanceMode: mode,
    organizationalUnit,
    namingTemplate,
    zoneLabel: txt(policy?.zone_name) || `Zone #${policy?.zone_id ?? '-'}`,
    tokensHint: TOKENS_HINT,
    showUseZoneValuesLink: true,
    canEditOverrideFields: mode === 'override'
  };

  const preview: ProvisioningPreviewModel = {
    status: resolvePreviewStatus(policy?.configuration_status),
    statusLabel: txt(policy?.configuration_message) || 'Ready to provision',
    rootCode,
    readGroup,
    writeGroup
  };

  const effective: EffectiveProvisioningModel = {
    sourceLabel: txt(policy?.policy_source_label) || 'Inherited',
    sourceVariant: resolveSourceVariant(policy?.policy_source),
    effectivePrefix: txt(effectiveNamingPolicy?.group_prefix) || 'B2S',
    effectiveOu: txt(policy?.effective_values?.ou_dn) || 'Not configured',
    effectiveNaming: txt(effectiveNamingPolicy?.template) || txt(policy?.effective_values?.naming_template) || 'Not configured',
    rootcodeStrategy: txt(effectiveNamingPolicy?.rootcode_strategy) || 'BASENAME',
    maxSamLength: txt(effectiveNamingPolicy?.max_sam_length) || '64',
    exampleReadGroup: readGroup,
    exampleWriteGroup: writeGroup
  };

  return {
    scope: 'storage-endpoint',
    configuration,
    preview,
    effective
  };
}
