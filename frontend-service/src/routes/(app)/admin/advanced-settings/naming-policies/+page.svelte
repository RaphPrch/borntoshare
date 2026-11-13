<script lang="ts">
  import NamingModelPicker from '$lib/components/provisioning/NamingModelPicker.svelte';
  import { checkNamingTemplate, exampleGroupName } from '$lib/utils/naming-templates';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import { clamp } from '$lib/utils/values';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';

  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import {
    putGlobalNamingPolicy,
    type GlobalNamingPolicy,
    type RootcodeStrategy
  } from '$lib/api/naming-policies';

  interface Props {
    data: {
    globalPolicy: Partial<GlobalNamingPolicy> | null;
  };
  }

  let { data }: Props = $props();

  const initialPolicy: GlobalNamingPolicy = {
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    group_prefix: data.globalPolicy?.group_prefix ?? 'B2S',
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    template: data.globalPolicy?.template ?? '{PREFIX}_{ROOTCODE}_{PERM}',
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    normalize_uppercase: Boolean(data.globalPolicy?.normalize_uppercase ?? true),
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    max_sam_length: Number(data.globalPolicy?.max_sam_length ?? 64),
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    replace_map_json: data.globalPolicy?.replace_map_json ?? {
      '\\': '_',
      '/': '_',
      ' ': '_',
      '-': '_'
    },
    // svelte-ignore state_referenced_locally (an initial value, read once as before)
    rootcode_strategy: (data.globalPolicy?.rootcode_strategy as RootcodeStrategy) ?? 'BASENAME'
  };

  let policy = $state<GlobalNamingPolicy>({ ...initialPolicy });

  const stringifyReplaceMap = (input: unknown): string => {
    if (typeof input === 'string') return input;
    if (input && typeof input === 'object') {
      try {
        return JSON.stringify(input, null, 2);
      } catch {
        return '{"\\":"_","/":"_"," ":"_","-":"_"}';
      }
    }
    return '{"\\":"_","/":"_"," ":"_","-":"_"}';
  };

  let replaceMapText = $state(stringifyReplaceMap(initialPolicy.replace_map_json));

  let saving = $state(false);
  let errorMsg = $state<string | null>(null);


  function normalizePolicy(input: GlobalNamingPolicy) {
    const normalizedMaxSamLength = clamp(Number(input.max_sam_length ?? 64), 8, 256);
    const normalizedTemplate = String(input.template ?? '').trim();
    const normalizedPrefix = String(input.group_prefix ?? '').trim();
    const normalizedRootcode = (input.rootcode_strategy ?? 'BASENAME') as RootcodeStrategy;
    return {
      group_prefix: normalizedPrefix,
      template: normalizedTemplate,
      normalize_uppercase: Boolean(input.normalize_uppercase),
      max_sam_length: normalizedMaxSamLength,
      rootcode_strategy: normalizedRootcode
    };
  }

  let initialSnapshot = $state(JSON.stringify(normalizePolicy(initialPolicy)));
  let initialReplaceMapSnapshot = $state(stringifyReplaceMap(initialPolicy.replace_map_json));

  let normalizedCurrent = $derived(normalizePolicy(policy));
  let templateCheck = $derived(checkNamingTemplate(normalizedCurrent.template.toUpperCase()));
  let parsedReplaceMap = $derived((() => {
    try {
      const parsed = JSON.parse(replaceMapText);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
      return parsed;
    } catch {
      return null;
    }
  })());
  let replaceMapError = $derived(parsedReplaceMap ? null : t('Invalid JSON for the replace map.'));
  let groupPrefixError = $derived(normalizedCurrent.group_prefix ? null : t('Prefix is required.'));
  let templateError =
    $derived(!normalizedCurrent.template
      ? t('The template is required.')
      : templateCheck.unknown.length
        ? t('Unknown token: {token}', { token: `{${templateCheck.unknown[0]}}` })
        : templateCheck.unique
          ? null
          : t('The template needs {PERM} and {ROOTCODE} or {RAND}'));
  let maxSamError =
    $derived(Number.isFinite(Number(policy.max_sam_length)) &&
    Number(policy.max_sam_length) >= 8 &&
    Number(policy.max_sam_length) <= 256
      ? null
      : t('Max sAM length must be between 8 and 256.'));
  // The sAM length and the folder code strategy keep their saved value (not shown: defaults that fit)
  let formHasErrors = $derived(Boolean(replaceMapError || groupPrefixError || templateError));
  let isDirty = $derived(JSON.stringify(normalizedCurrent) !== initialSnapshot || replaceMapText !== initialReplaceMapSnapshot);
  let canSave = $derived(!saving && isDirty && !formHasErrors);

  function mapToString(input: unknown): string {
    if (typeof input === 'string') return input;
    if (input && typeof input === 'object') return JSON.stringify(input);
    return '{"\\":"_","/":"_"," ":"_","-":"_"}';
  }

  async function saveGlobal() {
    if (!canSave || !parsedReplaceMap) return;
    saving = true;
    errorMsg = null;
    try {
      policy = await putGlobalNamingPolicy(fetch, {
        ...policy,
        ...normalizedCurrent,
        replace_map_json: mapToString(parsedReplaceMap)
      });
      replaceMapText = stringifyReplaceMap(policy.replace_map_json);
      initialSnapshot = JSON.stringify(normalizePolicy(policy));
      initialReplaceMapSnapshot = replaceMapText;
      toast.success(t('Global naming policy saved.'));
    } catch (e: unknown) {
      errorMsg = reportUiError(e, 'Failed to save global naming policy.', 'advanced_settings.naming_policy.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title={t('Naming policy')} subtitle={t('Global naming of the AD groups')} icon="bi-input-cursor-text">
  <h3 class="nm-section">{t('Name of the groups')}</h3>
  <div class="adv-form-grid">
    <SettingRow label={t('Prefix')} help="Global prefix added to generated groups.">
      <input class="b2s-input" bind:value={policy.group_prefix} />
      {#if groupPrefixError}
        <FieldError>{groupPrefixError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow
      label={t('Template')}
      help={t('Available tokens: {tokens}.', { tokens: '{PREFIX}, {ZONE}, {ROOTCODE}, {RAND}, {PERM}' })}
    >
      <NamingModelPicker template={policy.template} prefix={policy.group_prefix} onPick={(model) => (policy.template = model)} />
      <input class="b2s-input" bind:value={policy.template} />
      {#if templateError}
        <FieldError>{templateError}</FieldError>
      {:else}
        <small class="nm-example">{t('Example: {name}', { name: exampleGroupName(policy.template, { prefix: policy.group_prefix }) })}</small>
      {/if}
    </SettingRow>

  </div>

  <h3 class="nm-section">{t('Cleaning of the names')}</h3>
  <div class="adv-form-grid">
    <SettingRow label={t('Uppercase normalization')}>
      <label class="checkbox">
        <input type="checkbox" bind:checked={policy.normalize_uppercase} />
        <span>{t('Enabled')}</span>
      </label>
    </SettingRow>

    <SettingRow label={t('Replace map (JSON)')} help={t('Characters replaced in the names, e.g. {example}.', { example: '{"é": "e", " ": "_"}' })}>
      <textarea class="b2s-input" rows="4" bind:value={replaceMapText}></textarea>
      {#if replaceMapError}
        <FieldError>{replaceMapError}</FieldError>
      {/if}
    </SettingRow>
  </div>

  {#if errorMsg}
    <InlineAlert tone="error">{errorMsg}</InlineAlert>
  {/if}

  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" onclick={saveGlobal} disabled={!canSave}>
      {saving ? t('Saving…') : t('Save changes')}
    </button>
  </div>
</ConfigCard>

<style>
  .nm-section { margin: 4px 0 8px; font-size: var(--b2s-fs-sm); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--b2s-color-text-muted); }
  .nm-section:not(:first-of-type) { margin-top: 20px; }
</style>
