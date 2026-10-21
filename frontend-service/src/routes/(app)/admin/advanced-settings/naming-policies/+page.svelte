<script lang="ts">
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

  export let data: {
    globalPolicy: Partial<GlobalNamingPolicy> | null;
  };

  const initialPolicy: GlobalNamingPolicy = {
    group_prefix: data.globalPolicy?.group_prefix ?? 'B2S',
    template: data.globalPolicy?.template ?? '{PREFIX}_{ROOTCODE}_{PERM}',
    normalize_uppercase: Boolean(data.globalPolicy?.normalize_uppercase ?? true),
    max_sam_length: Number(data.globalPolicy?.max_sam_length ?? 64),
    replace_map_json: data.globalPolicy?.replace_map_json ?? {
      '\\': '_',
      '/': '_',
      ' ': '_',
      '-': '_'
    },
    rootcode_strategy: (data.globalPolicy?.rootcode_strategy as RootcodeStrategy) ?? 'BASENAME'
  };

  let policy: GlobalNamingPolicy = { ...initialPolicy };

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

  let replaceMapText = stringifyReplaceMap(initialPolicy.replace_map_json);

  let saving = false;
  let errorMsg: string | null = null;

  const templateTokens = ['{PREFIX}', '{ROOTCODE}', '{PERM}'];

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

  let initialSnapshot = JSON.stringify(normalizePolicy(initialPolicy));
  let initialReplaceMapSnapshot = stringifyReplaceMap(initialPolicy.replace_map_json);

  $: normalizedCurrent = normalizePolicy(policy);
  $: templateUpper = normalizedCurrent.template.toUpperCase();
  $: hasKnownToken = templateTokens.some((token) => templateUpper.includes(token));
  $: parsedReplaceMap = (() => {
    try {
      const parsed = JSON.parse(replaceMapText);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
      return parsed;
    } catch {
      return null;
    }
  })();
  $: replaceMapError = parsedReplaceMap ? null : t('JSON invalide pour Replace map.');
  $: groupPrefixError = normalizedCurrent.group_prefix ? null : t('Prefix is required.');
  $: templateError =
    !normalizedCurrent.template
      ? t('Le template est requis.')
      : hasKnownToken
        ? null
        : t('Template must contain at least one supported token.');
  $: maxSamError =
    Number.isFinite(Number(policy.max_sam_length)) &&
    Number(policy.max_sam_length) >= 8 &&
    Number(policy.max_sam_length) <= 256
      ? null
      : t('Max sAM length must be between 8 and 256.');
  $: formHasErrors = Boolean(replaceMapError || groupPrefixError || templateError || maxSamError);
  $: isDirty = JSON.stringify(normalizedCurrent) !== initialSnapshot || replaceMapText !== initialReplaceMapSnapshot;
  $: canSave = !saving && isDirty && !formHasErrors;

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

<ConfigCard title={t('Naming policy')} subtitle={t('Configuration globale de nommage des groupes AD')} icon="bi-input-cursor-text">
  <div class="adv-form-grid">
    <SettingRow label={t('Prefix')} help="Global prefix added to generated groups.">
      <input class="form-control" bind:value={policy.group_prefix} />
      {#if groupPrefixError}
        <FieldError>{groupPrefixError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow
      label={t('Template')}
      help={t('Available tokens: {tokens}.', { tokens: '{PREFIX}, {ROOTCODE}, {PERM}' })}
    >
      <input class="form-control" bind:value={policy.template} />
      {#if templateError}
        <FieldError>{templateError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow label={t('Max sAM length')}>
      <input class="form-control" type="number" min="8" max="256" bind:value={policy.max_sam_length} />
      {#if maxSamError}
        <FieldError>{maxSamError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow label={t('Uppercase normalization')}>
      <label class="checkbox">
        <input type="checkbox" bind:checked={policy.normalize_uppercase} />
        <span>{t('Enabled')}</span>
      </label>
    </SettingRow>

    <SettingRow label={t('Rootcode strategy')}>
      <select class="form-select" bind:value={policy.rootcode_strategy}>
        <option value="BASENAME">BASENAME</option>
        <option value="PATH_ALL">PATH_ALL</option>
      </select>
    </SettingRow>

    <SettingRow label={t('Replace map (JSON)')}>
      <textarea class="form-control" rows="4" bind:value={replaceMapText}></textarea>
      {#if replaceMapError}
        <FieldError>{replaceMapError}</FieldError>
      {/if}
    </SettingRow>
  </div>

  {#if errorMsg}
    <InlineAlert tone="error">{errorMsg}</InlineAlert>
  {/if}

  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={saveGlobal} disabled={!canSave}>
      {saving ? t('Saving…') : t('Save changes')}
    </button>
  </div>
</ConfigCard>
