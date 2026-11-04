<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveAdvancedSections, sendTestEmail } from '$lib/api/admin-advanced-settings';

  /** Advanced settings › Notifications: the e-mails of BornToShare (SMTP server, which notices) and the banner. */
  export let data: any;

  const stored = data.advanced?.notifications ?? {};
  let notif = {
    enabled: Boolean(stored.enabled),
    host: stored.host ?? '',
    port: stored.port ?? 587,
    security: stored.security ?? 'starttls',
    sender: stored.sender ?? '',
    username: stored.username ?? '',
    appUrl: stored.appUrl || (typeof location !== 'undefined' ? location.origin : ''),
    pendingToGuardians: stored.pendingToGuardians ?? true,
    decisionToRequester: stored.decisionToRequester ?? true,
    expiryReminderDays: stored.expiryReminderDays ?? 7
  };
  let password = '';
  const hasPassword = Boolean(stored.hasPassword);
  let savingMail = false;
  let testTo = data.me?.email ?? '';
  let testing = false;
  let testResult: { ok: boolean; text: string } | null = null;

  async function saveMail() {
    savingMail = true;
    try {
      await saveAdvancedSections(fetch, { notifications: { ...notif, port: Number(notif.port), expiryReminderDays: Number(notif.expiryReminderDays), ...(password ? { password } : {}) } });
      password = '';
      toast.success(t('Notifications saved.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the notifications.'), 'advanced_settings.notifications.save');
    } finally {
      savingMail = false;
    }
  }
  async function test() {
    testing = true;
    try {
      const result = await sendTestEmail(fetch, testTo.trim());
      testResult = result.ok ? { ok: true, text: t('Test e-mail sent to {to}.', { to: testTo }) } : { ok: false, text: t('The server refused: {error}', { error: result.error ?? '' }) };
    } catch (e) {
      reportUiError(e, t('The test e-mail could not be sent.'), 'advanced_settings.notifications.test');
    } finally {
      testing = false;
    }
  }

  const storedBanner = data.advanced?.banner ?? {};
  let banner = { enabled: Boolean(storedBanner.enabled), message: storedBanner.message ?? '', tone: storedBanner.tone ?? 'info' };
  let savingBanner = false;
  async function saveBanner() {
    savingBanner = true;
    try {
      await saveAdvancedSections(fetch, { banner });
      toast.success(banner.enabled ? t('Banner shown to every user.') : t('Banner hidden.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the banner.'), 'advanced_settings.banner.save');
    } finally {
      savingBanner = false;
    }
  }
</script>

<ConfigCard title={t('E-mails')} subtitle={t('Guardians told of a request, requesters of the decision and of an access about to end.')}>
  <div class="adv-form-grid">
    <SettingRow label={t('Send the e-mails')}>
      <div class="form-check form-switch"><input class="form-check-input" type="checkbox" role="switch" id="nt-on" bind:checked={notif.enabled} /><label class="form-check-label" for="nt-on">{notif.enabled ? t('Enabled') : t('Disabled')}</label></div>
    </SettingRow>
    <SettingRow label={t('SMTP server')}><input class="b2s-input" bind:value={notif.host} placeholder="smtp.corp.local" /></SettingRow>
    <SettingRow label={t('Port')}><input class="b2s-input" type="number" min="1" max="65535" bind:value={notif.port} /></SettingRow>
    <SettingRow label={t('Security')}><SegmentedFilter bind:value={notif.security} options={[{ key: 'starttls', label: 'STARTTLS' }, { key: 'tls', label: 'TLS' }, { key: 'none', label: t('None') }]} /></SettingRow>
    <SettingRow label={t('Sender')}><input class="b2s-input" type="email" bind:value={notif.sender} placeholder="borntoshare@corp.local" /></SettingRow>
    <SettingRow label={t('Account (optional)')}><input class="b2s-input" bind:value={notif.username} autocomplete="off" /></SettingRow>
    <SettingRow label={t('Password')}><input class="b2s-input" type="password" bind:value={password} placeholder={hasPassword ? t('Unchanged') : ''} autocomplete="new-password" /><small class="adv-hint">{t('Kept in the vault of BornToShare')}</small></SettingRow>
    <SettingRow label={t('Address of BornToShare in the e-mails')}><input class="b2s-input" bind:value={notif.appUrl} placeholder="https://b2s.corp.local" /></SettingRow>
  </div>
  <h3 class="nt__title">{t('Which e-mails')}</h3>
  <div class="nt__events">
    <label><input type="checkbox" bind:checked={notif.pendingToGuardians} /> {t('A new request: to the guardians of the folder')}</label>
    <label><input type="checkbox" bind:checked={notif.decisionToRequester} /> {t('A decision: to the requester, with the comment of the guardian')}</label>
    <label class="nt__reminder">{t('An access about to end: reminder')} <input class="b2s-input" type="number" min="0" max="60" bind:value={notif.expiryReminderDays} /> {t('days before (0: none)')}</label>
  </div>
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={saveMail} disabled={savingMail}><i class="bi bi-check2" aria-hidden="true"></i>{savingMail ? t('Saving…') : t('Save changes')}</button>
  </div>
  <div class="nt__test">
    <input class="b2s-input" type="email" bind:value={testTo} placeholder={t('Test address')} aria-label={t('Test address')} />
    <button class="b2s-btn b2s-btn-secondary" type="button" on:click={test} disabled={testing || !testTo.includes('@')}><i class="bi bi-envelope-check" aria-hidden="true"></i>{testing ? t('Sending…') : t('Send a test e-mail')}</button>
  </div>
  <small class="adv-hint">{t('The test uses the saved settings.')}</small>
  {#if testResult}<p class="nt__result" class:is-ok={testResult.ok} class:is-bad={!testResult.ok}>{testResult.text}</p>{/if}
</ConfigCard>

<ConfigCard title={t('Banner')} subtitle={t('A message shown at the top of every page, to every user (maintenance, incident).')}>
  <div class="adv-form-grid">
    <SettingRow label={t('Show the banner')}>
      <div class="form-check form-switch"><input class="form-check-input" type="checkbox" role="switch" id="bn-on" bind:checked={banner.enabled} /><label class="form-check-label" for="bn-on">{banner.enabled ? t('Shown') : t('Hidden')}</label></div>
    </SettingRow>
    <SettingRow label={t('Tone')}><SegmentedFilter bind:value={banner.tone} options={[{ key: 'info', label: t('Information') }, { key: 'warning', label: t('Warning') }, { key: 'danger', label: t('Incident') }]} /></SettingRow>
  </div>
  <SettingRow label={t('Message')}>
    <input class="b2s-input" maxlength="300" bind:value={banner.message} placeholder={t('e.g. Maintenance on Saturday from 8 to 10 am: requests are kept, accesses are set afterwards.')} />
  </SettingRow>
  {#if banner.message}<div class="nt__preview is-{banner.tone}"><i class="bi bi-megaphone" aria-hidden="true"></i>{banner.message}</div>{/if}
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={saveBanner} disabled={savingBanner || (banner.enabled && !banner.message.trim())}><i class="bi bi-check2" aria-hidden="true"></i>{savingBanner ? t('Saving…') : t('Save changes')}</button>
  </div>
</ConfigCard>

<style>
  .nt__title { margin: 14px 0 6px; font-size: var(--b2s-fs-md); font-weight: 600; }
  .nt__events { display: flex; flex-direction: column; gap: 8px; font-size: var(--b2s-fs-sm); }
  .nt__events label { display: flex; align-items: center; gap: 8px; }
  .nt__reminder input { width: 80px; }
  .nt__test { display: flex; gap: 8px; max-width: 520px; margin-top: 14px; }
  .nt__result { margin: 8px 0 0; padding: 10px 12px; border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); }
  .nt__result.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .nt__result.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .nt__preview { display: flex; align-items: center; gap: 8px; margin-top: 10px; padding: 10px 14px; border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); font-weight: 500; }
  .nt__preview.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .nt__preview.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .nt__preview.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
</style>
