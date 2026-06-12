<script lang="ts">
  import ConfigCard from '$lib/components/advanced-settings/v3/ConfigCard.svelte';
  import SettingRow from '$lib/components/advanced-settings/v3/SettingRow.svelte';

  import { toasts } from '$lib/stores/toast';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
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

  const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

  const toUiErrorMessage = (error: unknown, fallback: string, action: string): string => {
    const normalized = toAppError(error, { source: 'ui' });
    const appError = GENERIC_ERROR_MESSAGES.has(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
    logAppError(appError, { action });
    notifyError(appError);
    return appError.message;
  };

  const templateTokens = ['{PREFIX}', '{ROOTCODE}', '{PERM}'];

  const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));

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
  $: replaceMapError = parsedReplaceMap ? null : 'JSON invalide pour Replace map.';
  $: groupPrefixError = normalizedCurrent.group_prefix ? null : 'Prefix is required.';
  $: templateError =
    !normalizedCurrent.template
      ? 'Le template est requis.'
      : hasKnownToken
        ? null
        : 'Template must contain at least one supported token.';
  $: maxSamError =
    Number.isFinite(Number(policy.max_sam_length)) &&
    Number(policy.max_sam_length) >= 8 &&
    Number(policy.max_sam_length) <= 256
      ? null
      : 'Max sAM length must be between 8 and 256.';
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
      toasts.success('Global naming policy saved.');
    } catch (e: unknown) {
      errorMsg = toUiErrorMessage(e, 'Failed to save global naming policy.', 'advanced_settings.naming_policy.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title="Naming policy" subtitle="Configuration globale de nommage des groupes AD" icon="bi-input-cursor-text">
  <div class="adv-form-grid">
    <SettingRow label="Prefix" help="Global prefix added to generated groups.">
      <input class="form-control" bind:value={policy.group_prefix} />
      {#if groupPrefixError}
        <div class="adv-inline-error">{groupPrefixError}</div>
      {/if}
    </SettingRow>

    <SettingRow
      label="Template"
      help="Tokens disponibles : &#123;PREFIX&#125;, &#123;ROOTCODE&#125;, &#123;PERM&#125;."
    >
      <input class="form-control" bind:value={policy.template} />
      {#if templateError}
        <div class="adv-inline-error">{templateError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Max sAM length">
      <input class="form-control" type="number" min="8" max="256" bind:value={policy.max_sam_length} />
      {#if maxSamError}
        <div class="adv-inline-error">{maxSamError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Uppercase normalization">
      <label class="checkbox">
        <input type="checkbox" bind:checked={policy.normalize_uppercase} />
        <span>Enabled</span>
      </label>
    </SettingRow>

    <SettingRow label="Rootcode strategy">
      <select class="form-select" bind:value={policy.rootcode_strategy}>
        <option value="BASENAME">BASENAME</option>
        <option value="PATH_ALL">PATH_ALL</option>
      </select>
    </SettingRow>

    <SettingRow label="Replace map (JSON)">
      <textarea class="form-control" rows="4" bind:value={replaceMapText}></textarea>
      {#if replaceMapError}
        <div class="adv-inline-error">{replaceMapError}</div>
      {/if}
    </SettingRow>
  </div>

  {#if errorMsg}
    <div class="adv-inline-error adv-inline-error--block">{errorMsg}</div>
  {/if}

  <div class="adv-actions">
    <button class="btn btn-primary" type="button" on:click={saveGlobal} disabled={!canSave}>
      {saving ? 'Saving…' : 'Save changes'}
    </button>
  </div>
</ConfigCard>
