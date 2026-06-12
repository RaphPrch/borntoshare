import {
  buildProvisioningUpdatePayload,
  computeProvisioningSummary,
  createProvisioningDraft,
  extractProvisioningWarningMessages
} from './storage-endpoint-provisioning.mapper';
import { buildStorageEndpointProvisioningViewModel } from '../../components/provisioning/provisioning-policy.adapter';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testCreateDraftAndPayload(): void {
  const draft = createProvisioningDraft({
    storage_endpoint_id: 9,
    zone_id: 2,
    policy_mode: 'override',
    policy_source: 'endpoint',
    policy_source_label: 'Storage endpoint override',
    endpoint_values: {
      ou_dn: 'OU=Data,DC=corp,DC=local',
      naming_template: '{PREFIX}_{ROOTCODE}_{PERM}'
    },
    inherited_values: {
      ou_dn: 'OU=Inherited,DC=corp,DC=local',
      naming_template: '{PREFIX}-{ROOTCODE}-{PERM}'
    },
    effective_values: {
      ou_dn: 'OU=Inherited,DC=corp,DC=local',
      naming_template: '{PREFIX}-{ROOTCODE}-{PERM}'
    },
    effective_ou_status: 'configured',
    effective_template_status: 'configured',
    configuration_status: 'ready',
    configuration_message: 'ok',
    is_ready_to_provision: true,
    warnings: []
  });

  assert(draft.policyMode === 'override', 'draft mode should be override');
  assert(draft.ouDn === 'OU=Data,DC=corp,DC=local', 'draft OU should come from endpoint override');
  assert(
    draft.namingTemplate === '{PREFIX}_{ROOTCODE}_{PERM}',
    'draft naming template should come from endpoint override'
  );

  const payload = buildProvisioningUpdatePayload(draft);
  assert(payload.policy_mode === 'override', 'payload mode should be override');
  assert(payload.endpoint_values?.ou_dn === 'OU=Data,DC=corp,DC=local', 'endpoint OU should be set in override');
  assert(
    payload.endpoint_values?.naming_template === '{PREFIX}_{ROOTCODE}_{PERM}',
    'endpoint naming template should be set in override'
  );

  const inheritPayload = buildProvisioningUpdatePayload({
    policyMode: 'inherit',
    ouDn: 'ignored',
    namingTemplate: 'ignored'
  });
  assert(inheritPayload.policy_mode === 'inherit', 'inherit payload mode should remain inherit');
  assert(inheritPayload.endpoint_values?.ou_dn === null, 'inherit OU should be null');
  assert(inheritPayload.endpoint_values?.naming_template === null, 'inherit template should be null');
}

function testSummaryAndWarnings(): void {
  const summary = computeProvisioningSummary({
    storage_endpoint_id: 1,
    zone_id: 1,
    policy_mode: 'inherit',
    policy_source: 'zone',
    policy_source_label: 'Zone policy (Z1)',
    endpoint_values: { ou_dn: null, naming_template: null },
    inherited_values: { ou_dn: 'OU=Inherited,DC=corp,DC=local', naming_template: '{PREFIX}_{ROOTCODE}_{PERM}' },
    effective_values: { ou_dn: 'OU=Inherited,DC=corp,DC=local', naming_template: '{PREFIX}_{ROOTCODE}_{PERM}' },
    effective_ou_status: 'configured',
    effective_template_status: 'configured',
    configuration_status: 'ready',
    configuration_message: 'ready',
    is_ready_to_provision: true,
    warnings: [{ code: 'W1', level: 'warning', message: 'warning one' }],
    example_groups: {
      based_on_root_code: 'FINANCE_RW',
      read: 'B2S_FINANCE_RW_READ',
      write: 'B2S_FINANCE_RW_WRITE'
    }
  });

  assert(summary.modeLabel.includes('Inherited'), 'summary mode should mention inherited');
  assert(summary.policySource === 'Zone policy (Z1)', 'policy source should be propagated');
  assert(summary.effectiveOu.includes('OU=Inherited'), 'effective OU should be propagated');
  assert(summary.namingTemplate.includes('{PREFIX}'), 'template should be propagated');
  assert(summary.adProvisioningLabel === 'Sample groups generated', 'ad label should be generated');

  const warnings = extractProvisioningWarningMessages(
    {
      storage_endpoint_id: 1,
      zone_id: 1,
      policy_mode: 'inherit',
      policy_source: 'zone',
      policy_source_label: 'Zone policy (Z1)',
      endpoint_values: { ou_dn: null, naming_template: null },
      inherited_values: { ou_dn: null, naming_template: null },
      effective_values: { ou_dn: null, naming_template: null },
      effective_ou_status: 'missing',
      effective_template_status: 'missing',
      configuration_status: 'incomplete',
      configuration_message: 'missing',
      is_ready_to_provision: false,
      warnings: [{ code: 'W2', level: 'warning', message: 'missing OU' }]
    },
    0
  );

  assert(warnings.includes('missing OU'), 'warnings should include API message');
  assert(
    warnings.includes('No associated roots for this endpoint.'),
    'warnings should include empty-roots message'
  );
}

async function run(): Promise<void> {
  testCreateDraftAndPayload();
  testSummaryAndWarnings();
  testSharedProvisioningAdapterForEndpoint();
}

function testSharedProvisioningAdapterForEndpoint(): void {
  const vm = buildStorageEndpointProvisioningViewModel({
    storage_endpoint_id: 42,
    zone_id: 7,
    zone_name: 'Zone PAR-1',
    policy_mode: 'override',
    policy_source: 'endpoint',
    policy_source_label: 'Endpoint override',
    endpoint_override_enabled: true,
    endpoint_values: {
      ou_dn: 'OU=LYO1,OU=Storage',
      naming_template: '{PREFIX}-{ROOTCODE}-{PERM}'
    },
    inherited_values: {
      ou_dn: 'OU=PAR,OU=Storage',
      naming_template: '{PREFIX}-{ROOTCODE}-{PERM}'
    },
    effective_values: {
      ou_dn: 'OU=LYO1,OU=Storage',
      naming_template: '{PREFIX}-{ROOTCODE}-{PERM}'
    },
    effective_ou_status: 'configured',
    effective_template_status: 'configured',
    configuration_status: 'ready',
    configuration_message: 'Ready to provision',
    is_ready_to_provision: true,
    warnings: [],
    example_groups: {
      based_on_root_code: 'finance_rw',
      read: 'B2S_finance_rw_RX',
      write: 'B2S_finance_rw_RW'
    },
    effective_naming_policy: {
      group_prefix: 'B2S',
      template: '{PREFIX}-{ROOTCODE}-{PERM}',
      normalize_uppercase: true,
      max_sam_length: 64,
      rootcode_strategy: 'BASENAME'
    }
  });

  assert(vm.scope === 'storage-endpoint', 'vm scope should be storage-endpoint');
  assert(vm.configuration.inheritanceMode === 'override', 'vm should expose override mode');
  assert(vm.configuration.organizationalUnit.includes('OU=LYO1'), 'vm should expose endpoint OU');
  assert(vm.preview.status === 'ready', 'vm preview status should map to ready');
  assert(vm.effective.sourceVariant === 'endpoint', 'vm should expose endpoint source variant');
  assert(vm.effective.effectivePrefix === 'B2S', 'vm should expose effective group prefix');
  assert(vm.effective.rootcodeStrategy === 'BASENAME', 'vm should expose rootcode strategy');
  assert(vm.effective.maxSamLength === '64', 'vm should expose max SAM length');
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
