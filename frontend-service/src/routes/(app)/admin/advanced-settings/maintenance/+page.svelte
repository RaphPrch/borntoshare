<script lang="ts">
  import ConfigCard from '$lib/components/advanced-settings/v3/ConfigCard.svelte';
  import SettingRow from '$lib/components/advanced-settings/v3/SettingRow.svelte';

  import { toasts } from '$lib/stores/toast';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
  import { saveMaintenanceConfig } from '$lib/api/admin-advanced-settings';

  export let data: any;
  const settings = data.settings;

  const initialMaintenance = {
    enabled: Boolean(settings.maintenance.enabled),
    message: String(settings.maintenance.message ?? ''),
    allowedCidrs: Array.isArray(settings.maintenance.allowedCidrs) ? [...settings.maintenance.allowedCidrs] : []
  };

  let form = { ...initialMaintenance };
  let allowedCidrsText = initialMaintenance.allowedCidrs.join(', ');
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

  const cidrRegex = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\/(3[0-2]|[12]?\d)$/;

  const parseCidrs = (raw: string) =>
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

  const normalize = (input: typeof form, cidrsText: string) => ({
    enabled: Boolean(input.enabled),
    message: String(input.message ?? '').trim(),
    allowedCidrs: parseCidrs(cidrsText)
  });

  let initialSnapshot = JSON.stringify(normalize(initialMaintenance, allowedCidrsText));

  $: parsedCidrs = parseCidrs(allowedCidrsText);
  $: invalidCidrs = parsedCidrs.filter((c) => !cidrRegex.test(c));
  $: cidrError = invalidCidrs.length ? `CIDR invalide: ${invalidCidrs.join(', ')}` : null;
  $: messageError = form.message.trim() ? null : 'Le message de maintenance est requis.';
  $: hasErrors = Boolean(cidrError || messageError);
  $: isDirty = JSON.stringify(normalize(form, allowedCidrsText)) !== initialSnapshot;
  $: canSave = !saving && isDirty && !hasErrors;

  async function save() {
    if (!canSave) return;
    saving = true;
    errorMsg = null;
    try {
      const payload = normalize(form, allowedCidrsText);
      await saveMaintenanceConfig(fetch, payload);
      settings.maintenance = { ...settings.maintenance, ...payload };
      form = { ...payload };
      allowedCidrsText = payload.allowedCidrs.join(', ');
      initialSnapshot = JSON.stringify(normalize(payload, allowedCidrsText));
      toasts.success('Maintenance settings saved.');
    } catch (e: unknown) {
      errorMsg = toUiErrorMessage(e, 'Unable to save right now.', 'advanced_settings.maintenance.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title="Maintenance" subtitle="Mode maintenance de la plateforme" icon="bi-tools">
  <div class="adv-form-grid">
    <SettingRow label="Enable maintenance mode">
      <label class="checkbox">
        <input type="checkbox" bind:checked={form.enabled} />
        <span>Enabled</span>
      </label>
    </SettingRow>

    <SettingRow label="Maintenance message">
      <input class="form-control" type="text" bind:value={form.message} />
      {#if messageError}
        <div class="adv-inline-error">{messageError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Allowed CIDRs" help="Comma-separated list. Only these IPs can access during maintenance.">
      <input class="form-control" type="text" bind:value={allowedCidrsText} placeholder="10.0.0.0/24, 192.168.5.0/24" />
      {#if cidrError}
        <div class="adv-inline-error">{cidrError}</div>
      {/if}
    </SettingRow>
  </div>

  {#if errorMsg}
    <div class="adv-inline-error adv-inline-error--block">{errorMsg}</div>
  {/if}

  <div class="adv-actions">
    <button class="btn btn-primary" type="button" on:click={save} disabled={!canSave}>
      {saving ? 'Saving…' : 'Save changes'}
    </button>
  </div>
</ConfigCard>
