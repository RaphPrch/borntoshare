export type ProvisioningScope = 'zone' | 'storage-endpoint';

export type ProvisioningConfigurationModel = {
  scope: ProvisioningScope;
  inheritanceMode?: 'inherit' | 'override';
  inheritanceModeLocked?: boolean;
  organizationalUnit: string;
  namingTemplate: string;
  zoneLabel?: string;
  tokensHint?: string;
  showUseZoneValuesLink?: boolean;
  canEditOverrideFields?: boolean;
  onChangeInheritanceMode?: (mode: 'inherit' | 'override') => void;
  onChangeOrganizationalUnit?: (value: string) => void;
  onChangeNamingTemplate?: (value: string) => void;
  onUseZoneValues?: () => void;
  onSavePolicy?: () => void;
  savePolicyLabel?: string;
  savePolicyDisabled?: boolean;
  savePolicyBusy?: boolean;
};

export type ProvisioningPreviewModel = {
  status: 'ready' | 'warning' | 'invalid';
  statusLabel: string;
  rootCode: string;
  readGroup: string;
  writeGroup: string;
};

export type EffectiveProvisioningModel = {
  sourceLabel: string;
  sourceVariant: 'global' | 'zone' | 'endpoint' | 'inherited';
  effectivePrefix?: string;
  effectiveOu: string;
  effectiveNaming: string;
  rootcodeStrategy?: string;
  maxSamLength?: string;
  exampleReadGroup: string;
  exampleWriteGroup: string;
};

export type ProvisioningPolicyScreenProps = {
  scope: ProvisioningScope;
  title?: string;
  saveLabel?: string;
  configuration: ProvisioningConfigurationModel;
  preview: ProvisioningPreviewModel;
  effective: EffectiveProvisioningModel;
  onSave?: () => void;
  saveDisabled?: boolean;
  saveBusy?: boolean;
  errorMessage?: string | null;
  showUnsaved?: boolean;
  showEffectiveSave?: boolean;
  showEffectivePreview?: boolean;
};

export type ProvisioningPolicyViewModel = {
  scope: ProvisioningScope;
  configuration: ProvisioningConfigurationModel;
  preview: ProvisioningPreviewModel;
  effective: EffectiveProvisioningModel;
};
