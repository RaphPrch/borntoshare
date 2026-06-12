import type {
  StorageEndpointProvisioningPolicy,
  StorageEndpointProvisioningUpdatePayload
} from '$lib/api/storage-endpoints';

export type EndpointProvisioningDraft = {
  policyMode: 'inherit' | 'override';
  ouDn: string;
  namingTemplate: string;
};

const txt = (value: unknown): string => String(value ?? '').trim();

export function createProvisioningDraft(
  policy: StorageEndpointProvisioningPolicy | null | undefined
): EndpointProvisioningDraft {
  const isOverride = policy?.policy_mode === 'override';
  const endpointOu = String(policy?.endpoint_values?.ou_dn ?? '');
  const endpointTemplate = String(policy?.endpoint_values?.naming_template ?? '');

  return {
    policyMode: isOverride ? 'override' : 'inherit',
    ouDn: isOverride ? endpointOu : String(policy?.inherited_values?.ou_dn ?? endpointOu),
    namingTemplate: isOverride
      ? endpointTemplate
      : String(policy?.inherited_values?.naming_template ?? endpointTemplate)
  };
}

export function buildProvisioningUpdatePayload(
  draft: EndpointProvisioningDraft
): StorageEndpointProvisioningUpdatePayload {
  const mode = draft.policyMode;
  return {
    policy_mode: mode,
    endpoint_values: {
      ou_dn: mode === 'override' ? txt(draft.ouDn) || null : null,
      naming_template: mode === 'override' ? txt(draft.namingTemplate) || null : null
    }
  };
}

export function computeProvisioningSummary(
  policy: StorageEndpointProvisioningPolicy | null | undefined
): {
  modeLabel: string;
  policySource: string;
  effectiveOu: string;
  namingTemplate: string;
  adProvisioningLabel: string;
} {
  return {
    modeLabel: policy?.policy_mode === 'override' ? 'Endpoint override' : 'Inherited from zone/global',
    policySource: policy?.policy_source_label ?? 'Policy not configured',
    effectiveOu: txt(policy?.effective_values?.ou_dn) || 'Not configured',
    namingTemplate: txt(policy?.effective_values?.naming_template) || 'Not configured',
    adProvisioningLabel:
      policy?.example_groups?.read && policy?.example_groups?.write
        ? 'Sample groups generated'
        : 'Not yet provisioned'
  };
}

export function extractProvisioningWarningMessages(
  policy: StorageEndpointProvisioningPolicy | null | undefined,
  selectedRootsCount: number
): string[] {
  const warnings = (policy?.warnings ?? [])
    .map((item) => txt(item?.message))
    .filter(Boolean);

  if (selectedRootsCount <= 0) {
    warnings.push('No associated roots for this endpoint.');
  }

  return warnings;
}
