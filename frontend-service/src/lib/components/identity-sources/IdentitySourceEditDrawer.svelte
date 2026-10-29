<script lang="ts">
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import { t } from '$lib/i18n';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { updateIdentitySource, type IdentitySourcePayload } from '$lib/api/identity-sources';
  import { resolveCredentials } from '$lib/api/credentials';
  import {
    formatRelativeTimestamp,
    identitySourceTypeLabel,
    type IdentitySourceCardVM
  } from '$lib/mappers/identity-sources.mapper';
  import { testIdentitySourceConnection } from '$lib/jobs/identity-source-test';
  import { lastSyncLabel, sourceIconClass, toneClass } from '$lib/utils/identity-sources';
  import type { IdentitySourceRow } from '$lib/types/identity-sources';
  import { toast } from '$lib/stores/toast';
  import { notifyError, toUiAppError } from '$lib/errors';
  import ServiceAccountOverride from './ServiceAccountOverride.svelte';
  import {
    buildServiceAccountsPayload,
    domainFromBaseDn,
    draftsForCapabilities,
    emptyServiceAccountDrafts,
    serviceAccountDraftError,
    serviceAccountDraftsFrom,
    testServiceAccount,
    type ServiceAccountDrafts,
    type ServiceAccountPurpose
  } from '$lib/utils/service-accounts';

  /** Source to edit, already merged with its internal metadata. Only AD / LDAP sources exist. */
  export let open = false;
  export let source: IdentitySourceRow | null = null;
  export let sourceCard: IdentitySourceCardVM | null = null;
  export let onClose: () => void;
  export let onSaved: (sourceId: number) => Promise<void> | void = () => {};

  type ProbeResult = {
    ok: boolean;
    message: string;
    status?: string | null;
    jobId?: string | number | null;
    result?: Record<string, unknown> | null;
    checkedAt?: string | null;
  };

  const emptyForm = () => ({
    display_name: '',
    protocol: 'ldaps' as 'ldap' | 'ldaps',
    host: '',
    port: 636,
    base_dn: '',
    domain_name: '',
    bind_dn: '',
    bind_password_ref: '',
    bind_password: '',
    capabilities: { auth: true, import_groups: true, snapshot_enabled: false, provisioning: false },
    service_accounts: emptyServiceAccountDrafts(),
    is_active: true
  });

  let form = emptyForm();
  let initializedFor: IdentitySourceRow | null = null;
  let showErrors = false;
  let showPassword = false;
  let saving = false;
  let probeRunning = false;
  let probeResult: ProbeResult | null = null;
  let actionError: string | null = null;

  const normalize = (value: unknown) => String(value ?? '').trim();
  const defaultPort = (protocol: string | undefined) => (protocol === 'ldap' ? 389 : 636);

  $: if (open && source && source !== initializedFor) {
    initializedFor = source;
    form = {
      display_name: normalize(source.display_name ?? source.name),
      // Sources saved as "ldap" on port 636 do use LDAPS
      protocol: source.protocol === 'ldap' && Number(source.port) !== 636 ? 'ldap' : 'ldaps',
      host: source.host ?? '',
      port: source.port ?? defaultPort(source.protocol),
      base_dn: source.base_dn ?? '',
      domain_name: source.domain_name ?? '',
      bind_dn: source.bind_dn ?? '',
      bind_password_ref: source.bind_password_ref ?? '',
      bind_password: '',
      capabilities: {
        auth: source.capabilities?.auth ?? true,
        import_groups: source.capabilities?.import_groups ?? true,
        snapshot_enabled: source.capabilities?.snapshot_enabled ?? false,
        provisioning: source.capabilities?.provisioning ?? false
      },
      service_accounts: serviceAccountDraftsFrom(source.service_accounts),
      is_active: source.is_active ?? true
    };
    showErrors = false;
    showPassword = false;
    probeResult = null;
    probeRunning = false;
    actionError = null;
  }
  $: if (!open) initializedFor = null;

  const setProtocol = (value: 'ldap' | 'ldaps') => {
    form.protocol = value;
    form.port = defaultPort(value);
  };

  const accountsChanged = (src: IdentitySourceRow, drafts: ServiceAccountDrafts): boolean => {
    const stored = serviceAccountDraftsFrom(src.service_accounts);
    return (Object.keys(drafts) as (keyof ServiceAccountDrafts)[]).some(
      (purpose) =>
        drafts[purpose].dedicated !== stored[purpose].dedicated ||
        (drafts[purpose].dedicated &&
          (normalize(drafts[purpose].bind_dn) !== normalize(stored[purpose].bind_dn) || normalize(drafts[purpose].password) !== ''))
    );
  };

  const hasChanges = (src: IdentitySourceRow | null, f: typeof form): boolean => {
    if (!src) return false;
    return (
      normalize(f.display_name) !== normalize(src.display_name ?? src.name) ||
      f.protocol !== (src.protocol || 'ldaps') ||
      normalize(f.host) !== normalize(src.host) ||
      Number(f.port) !== Number(src.port || defaultPort(src.protocol)) ||
      normalize(f.base_dn) !== normalize(src.base_dn) ||
      normalize(f.domain_name) !== normalize(src.domain_name) ||
      normalize(f.bind_dn) !== normalize(src.bind_dn) ||
      normalize(f.bind_password_ref) !== normalize(src.bind_password_ref) ||
      normalize(f.bind_password) !== '' ||
      f.capabilities.auth !== (src.capabilities?.auth ?? true) ||
      f.capabilities.import_groups !== (src.capabilities?.import_groups ?? true) ||
      f.capabilities.snapshot_enabled !== (src.capabilities?.snapshot_enabled ?? false) ||
      f.capabilities.provisioning !== (src.capabilities?.provisioning ?? false) ||
      accountsChanged(src, f.service_accounts) ||
      f.is_active !== (src.is_active ?? true)
    );
  };

  $: requiredOk =
    !!normalize(form.display_name) &&
    !!normalize(form.host) &&
    !!normalize(form.base_dn) &&
    !!normalize(form.bind_dn) &&
    !serviceAccountDraftError(draftsForCapabilities(form.service_accounts, form.capabilities));
  $: suggestedDomain = domainFromBaseDn(form.base_dn);
  $: canSave = requiredOk && hasChanges(source, form);

  $: endpointLabel = (() => {
    const host = normalize(form.host || source?.host);
    const port = Number(form.port || source?.port || 0);
    return host ? `${host}${port > 0 ? `:${port}` : ''}` : '—';
  })();

  $: healthLabel = probeRunning
    ? t('Checking')
    : probeResult
      ? (probeResult.ok ? t('Healthy') : t('Unhealthy'))
      : sourceCard?.healthLabel ?? t('Unknown');

  $: healthTone = probeRunning
    ? 'info'
    : probeResult
      ? (probeResult.ok ? 'success' : 'error')
      : sourceCard?.healthTone ?? 'muted';

  $: checkedLabel = (() => {
    if (probeRunning) return t('Testing now');
    const checked = probeResult?.checkedAt ?? source?.last_probe_at ?? null;
    return checked ? t('Last tested {formatRelativeTimestamp}', { formatRelativeTimestamp: formatRelativeTimestamp(checked) }) : t('No test yet');
  })();

  const probeResultValue = (keys: string[]): unknown => {
    const result = probeResult?.result;
    if (!result || typeof result !== 'object') return undefined;
    for (const key of keys) {
      if (key in result) return result[key];
    }
    return undefined;
  };

  const checkTone = (value: unknown) => (value === true ? 'success' : value === false ? 'error' : 'muted');
  const checkIcon = (value: unknown) => (value === true ? 'bi-check-lg' : value === false ? 'bi-x-lg' : 'bi-dash');

  $: validationChecks = (() => {
    const status = normalize(probeResult?.status ?? source?.status).toLowerCase();
    const lastMessage = normalize(probeResult?.message ?? source?.last_probe_message);
    const ok = probeResult?.ok ?? ['active', 'healthy', 'connected', 'online', 'success', 'succeeded'].includes(status);
    const bindOk = probeResultValue(['bind_ok', 'ldap_bind_ok', 'auth_ok']);
    const isLdaps = form.protocol === 'ldaps';
    const tlsOk = isLdaps ? probeResultValue(['tls_ok', 'certificate_ok', 'cert_ok']) : undefined;
    const duration = probeResultValue(['duration_ms', 'response_time_ms', 'elapsed_ms']);
    const tlsVerified = probeResultValue(['tls_verified']);
    const notReported = t('Not reported by the latest probe.');

    return [
      {
        key: 'connection',
        title: ok ? t('Connection successful') : t('Connection failed'),
        description: lastMessage || (ok ? t('The server responded successfully.') : t('The server did not validate the connection.')),
        tone: ok ? 'success' : 'error',
        icon: ok ? 'bi-check-lg' : 'bi-x-lg'
      },
      {
        key: 'bind',
        title: bindOk === true ? t('LDAP bind succeeded') : bindOk === false ? t('LDAP bind failed') : t('LDAP bind'),
        description:
          bindOk === true
            ? t('The service account bind was successful.')
            : bindOk === false
              ? t('The service account bind failed.')
              : notReported,
        tone: checkTone(bindOk),
        icon: checkIcon(bindOk)
      },
      {
        key: 'certificate',
        title: !isLdaps
          ? t('TLS certificate')
          : tlsOk === true && tlsVerified === false
            ? t('Encrypted connection')
            : tlsOk === true
            ? t('Server certificate valid')
            : tlsOk === false
              ? t('Server certificate invalid')
              : t('Server certificate'),
        description: !isLdaps
          ? t('Not applicable for LDAP.')
          : tlsOk === true && tlsVerified === false
            ? t('Encrypted, but the certificate is not checked: LDAP_TLS_VERIFY is off on the worker.')
            : tlsOk === true
            ? t('The server certificate is trusted and valid.')
            : tlsOk === false
              ? t('The server certificate could not be validated.')
              : notReported,
        // Encrypted but not checked: not a failure, not a validated certificate either
        tone: tlsOk === true && tlsVerified === false ? 'muted' : checkTone(tlsOk),
        icon: tlsOk === true && tlsVerified === false ? 'bi-shield-exclamation' : checkIcon(tlsOk)
      },
      {
        key: 'response',
        title: t('Response time'),
        description: normalize(duration) ? `${normalize(duration)} ms` : notReported,
        tone: 'muted',
        icon: 'bi-speedometer2'
      }
    ];
  })();

  const connectionPayload = () => ({
    type: 'ad' as const,
    name: normalize(form.display_name),
    protocol: form.protocol,
    host: normalize(form.host) || null,
    port: form.port ? Number(form.port) : null,
    base_dn: normalize(form.base_dn) || null,
    domain_name: normalize(form.domain_name) || null,
    bind_dn: normalize(form.bind_dn) || null,
    bind_password_ref: normalize(form.bind_password_ref) || null,
    bind_password: normalize(form.bind_password) || null,
    capabilities: {
      auth: form.capabilities.auth,
      import_groups: form.capabilities.import_groups,
      snapshot_enabled: form.capabilities.snapshot_enabled,
      provisioning: form.capabilities.provisioning
    },
    is_active: form.is_active
  });

  const testAccount = (purpose: ServiceAccountPurpose): Promise<boolean> => {
    const connection = connectionPayload();
    return testServiceAccount(
      fetch,
      { ...connection, capabilities: { ...connection.capabilities, auth_mode: source?.capabilities?.auth_mode === 'kerberos' ? 'kerberos' : 'ntlm' } },
      form.service_accounts[purpose],
      {
        purpose,
        secretNameBase: `identity-source/${connection.protocol}/${connection.host || connection.name || 'ad'}`,
        storedRef: source?.service_accounts?.[purpose]?.bind_password_ref ?? null
      }
    );
  };

  const handleSave = async () => {
    if (!source) return;
    if (!canSave) {
      showErrors = true;
      actionError = 'Please fill in required fields.';
      return;
    }
    saving = true;
    actionError = null;
    try {
      const payload = connectionPayload();
      // Only new passwords are stored; a disabled capability drops its dedicated account
      const service_accounts = await buildServiceAccountsPayload(
        fetch,
        draftsForCapabilities(form.service_accounts, form.capabilities),
        `identity-source/${payload.protocol}/${payload.host || payload.name || 'ad'}`
      );
      if (!payload.bind_password_ref && payload.bind_password) {
        const resolved = await resolveCredentials(fetch, {
          username: payload.bind_dn,
          password: payload.bind_password,
          secret_ref: null
        }, { secretName: `identity-source/${payload.protocol}/${payload.host || payload.name || 'ad'}`, mode: 'create' });
        payload.bind_password_ref = resolved.secret_ref ?? null;
        payload.bind_password = null;
      }
      await updateIdentitySource(fetch, source.id, { ...payload, service_accounts } as Partial<IdentitySourcePayload>);
      toast.success(t('Source updated.'));
      const savedId = source.id;
      onClose();
      await onSaved(savedId);
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Unable to update'), 'ui', {
        action: 'identity_sources.update_source',
        sourceId: source.id
      });
      actionError = appError.message;
      notifyError(appError);
    } finally {
      saving = false;
    }
  };

  const handleTestConnection = async () => {
    if (!source) return;
    if (!normalize(form.host) || !normalize(form.base_dn) || !normalize(form.bind_dn)) {
      showErrors = true;
      actionError = 'Please fill in required fields before testing.';
      return;
    }
    probeRunning = true;
    actionError = null;
    probeResult = null;
    try {
      const payload = connectionPayload();
      const result = await testIdentitySourceConnection(fetch, {
        ...payload,
        bind_password_ref: payload.bind_password_ref || source.bind_password_ref || null,
        identity_source_id: source.id,
        capabilities: { ...payload.capabilities, auth_mode: source.capabilities?.auth_mode ?? 'ntlm' }
      } as IdentitySourcePayload & { bind_password?: string | null });
      const firstCheck = result.checks[0] ?? null;
      probeResult = {
        ok: result.ok,
        status: result.status ?? null,
        jobId: result.job_id ?? null,
        message: normalize(firstCheck?.message) || (result.ok ? t('Probe OK') : t('Probe failed')),
        result: result.details ?? null,
        checkedAt: new Date().toISOString()
      };
      if (result.ok) toast.success(t('Connection validated.'));
      else toast.error(probeResult.message);
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Connection test failed.'), 'ui', {
        action: 'identity_sources.edit_test_connection',
        sourceId: source.id
      });
      probeResult = {
        ok: false,
        status: 'failed',
        message: appError.message,
        result: null,
        checkedAt: new Date().toISOString()
      };
      notifyError(appError);
    } finally {
      probeRunning = false;
    }
  };
</script>

<Drawer
  {open}
  size="lg"
  title={t('Edit identity source')}
  subtitle={source?.display_name ?? source?.name ?? t('Identity source')}
  iconClass={`bi ${sourceIconClass(sourceCard)}`}
  ariaLabelledby="identity-source-edit-title"
  {onClose}
>
  <svelte:fragment slot="header-meta">
    <StatusBadge
      status={form.is_active ? 'active' : 'disabled'}
      label={form.is_active ? t('Active') : t('Disabled')}
      variant={form.is_active ? 'success' : 'disabled'}
      compact={true}
    />
    {#if source?.used}
      <StatusBadge status="in-use" label={t('In use')} variant="info" compact={true} />
    {/if}
  </svelte:fragment>

  <div class="identity-edit-shell">
    <section class="identity-edit-summary" aria-label={t('Identity source summary')}>
      <div>
        <span>{t('Type')}</span>
        <strong>{sourceCard?.typeLabel ?? identitySourceTypeLabel('ad')}</strong>
      </div>
      <div>
        <span>{t('Endpoint')}</span>
        <strong>{endpointLabel}</strong>
      </div>
      <div>
        <span>{t('Status')}</span>
        <strong class={`identity-edit-status ${toneClass(healthTone)}`}>
          <i class="bi bi-circle-fill" aria-hidden="true"></i>
          {healthLabel}
        </strong>
      </div>
      <div>
        <span>{t('Last sync')}</span>
        <strong>{lastSyncLabel(source)}</strong>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>{t('Connection')}</h3>
        <p>{t('Core settings required to validate the source.')}</p>
      </div>
      <div class="identity-edit-grid">
        <label class="identity-edit-field">
          <span>{t('Display name')}</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.display_name)} bind:value={form.display_name} />
          {#if showErrors && !normalize(form.display_name)}
            <FieldError>{t('Required')}</FieldError>
          {/if}
        </label>
        <div class="identity-edit-field">
          <span>{t('Encryption')}</span>
          <div class="form-check form-switch">
            <input
              id="identity-edit-ldaps"
              class="form-check-input"
              type="checkbox"
              checked={form.protocol === 'ldaps'}
              on:change={(event) => setProtocol(event.currentTarget.checked ? 'ldaps' : 'ldap')}
            />
            <label class="form-check-label" for="identity-edit-ldaps">{t('Use LDAPS (encrypted connection)')}</label>
          </div>
          <small class="identity-edit-hint">
            {form.protocol === 'ldaps'
              ? t('LDAPS · port 636. Recommended in production.')
              : t('LDAP · port 389. The password of the service account travels unencrypted.')}
          </small>
        </div>
        <label class="identity-edit-field">
          <span>{t('Hostname / IP')}</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.host)} bind:value={form.host} />
          {#if showErrors && !normalize(form.host)}
            <FieldError>{t('Required')}</FieldError>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>{t('Port')}</span>
          <input class="identity-edit-input" type="number" min="1" max="65535" bind:value={form.port} />
        </label>
        <label class="identity-edit-field identity-edit-field--full">
          <span>{t('Base DN')}</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.base_dn)} bind:value={form.base_dn} />
          {#if showErrors && !normalize(form.base_dn)}
            <FieldError>{t('Required')}</FieldError>
          {/if}
        </label>
        <label class="identity-edit-field identity-edit-field--full">
          <span>{t('Domain name')}</span>
          <input class="identity-edit-input" bind:value={form.domain_name} placeholder={suggestedDomain || 'example.test'} />
          <small class="identity-edit-hint">{t('Users can sign in as user@domain or DOMAIN\\user. Empty: derived from the base DN.')}</small>
        </label>
        <div class="identity-edit-note identity-edit-field--full">
          <i class="bi bi-info-circle" aria-hidden="true"></i>
          {form.protocol === 'ldaps'
            ? t('LDAPS selected: port set to 636 automatically.')
            : t('LDAP selected: port set to 389 automatically.')}
        </div>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>{t('Credentials')}</h3>
        <p>{t('Main service account. Used by every capability that has no dedicated account.')}</p>
      </div>
      <div class="identity-edit-grid">
        <label class="identity-edit-field">
          <span>{t('Bind DN')}</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.bind_dn)} bind:value={form.bind_dn} />
          {#if showErrors && !normalize(form.bind_dn)}
            <FieldError>{t('Required')}</FieldError>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>{t('Bind password')}</span>
          <div class="identity-edit-input-action">
            <input
              class="identity-edit-input"
              type={showPassword ? 'text' : 'password'}
              bind:value={form.bind_password}
              placeholder={form.bind_password_ref ? t('Stored secret unchanged') : t('AD account password')}
            />
            <button
              type="button"
              aria-label={showPassword ? t('Hide password') : t('Show password')}
              on:click={() => (showPassword = !showPassword)}
            >
              <i class={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
          </div>
          <small class="identity-field-help">{t('Stored securely in Secret Broker.')}</small>
        </label>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>{t('Capabilities')}</h3>
        <p>{t('Enable features available for this source.')}</p>
      </div>
      <div class="identity-edit-capabilities">
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-person-check" aria-hidden="true"></i></span>
          <span>
            <strong>{t('Authenticate users')}</strong>
            <small>{t('Allow this source to authenticate users.')}</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.auth} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>
          <span>
            <strong>{t('Import groups')}</strong>
            <small>{t('Import groups from this source.')}</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.import_groups} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-cloud-arrow-down" aria-hidden="true"></i></span>
          <span>
            <strong>{t('Snapshot inventory')}</strong>
            <small>{t('Needed to search and import users and groups of this source.')}</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.snapshot_enabled} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-people" aria-hidden="true"></i></span>
          <span>
            <strong>{t('Manage AD groups')}</strong>
            <small>{t('Create AD groups and add members when access requests are approved.')}</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.provisioning} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-shield-check" aria-hidden="true"></i></span>
          <span>
            <strong>{t('Source active')}</strong>
            <small>{t('Enable this source across the system.')}</small>
          </span>
          <input type="checkbox" bind:checked={form.is_active} />
        </label>
      </div>
    </section>

    {#if form.capabilities.snapshot_enabled || form.capabilities.auth || form.capabilities.provisioning}
      <section class="identity-edit-card">
        <div class="identity-edit-section-head">
          <h3>{t('Service accounts per capability')}</h3>
          <p>{t('Least privilege: give each capability only the rights it needs.')}</p>
        </div>
        <div class="identity-edit-accounts">
          {#if form.capabilities.snapshot_enabled}
            <ServiceAccountOverride
              idPrefix="edit-sa-snapshot"
              placeholder="svc-read@example.test"
              icon="bi-cloud-arrow-down"
              title={t('Snapshot inventory')}
              description={t('Read-only account that collects users, groups and memberships.')}
              bind:draft={form.service_accounts.snapshot}
              onTest={() => testAccount('snapshot')}
              {showErrors}
            />
          {/if}
          {#if form.capabilities.auth}
            <ServiceAccountOverride
              idPrefix="edit-sa-auth"
              placeholder="svc-auth@example.test"
              icon="bi-person-check"
              title={t('Authenticate users')}
              description={t('Read-only account that finds the user before checking the password.')}
              bind:draft={form.service_accounts.auth}
              onTest={() => testAccount('auth')}
              {showErrors}
            />
          {/if}
          {#if form.capabilities.provisioning}
            <ServiceAccountOverride
              idPrefix="edit-sa-provisioning"
              placeholder="svc-prov@example.test"
              icon="bi-people"
              title={t('Manage AD groups')}
              description={t('Account delegated on the target OUs: create groups and change their members.')}
              bind:draft={form.service_accounts.provisioning}
              onTest={() => testAccount('provisioning')}
              {showErrors}
            />
          {/if}
        </div>
      </section>
    {/if}

    <section class="identity-edit-card">
      <div class="identity-edit-section-head identity-edit-section-head--inline">
        <div>
          <h3>{t('Validation')}</h3>
          <p>{t('Results from the most recent connection test.')}</p>
        </div>
        <span class={`identity-edit-tested ${toneClass(healthTone)}`}>
          <i class="bi bi-circle-fill" aria-hidden="true"></i>
          {checkedLabel}
        </span>
      </div>
      <div class="identity-edit-validation" class:is-error={probeResult?.ok === false} class:is-success={probeResult?.ok === true}>
        {#each validationChecks as check (check.key)}
          <article class={`identity-edit-validation-item is-${check.tone}`}>
            <span><i class={`bi ${check.icon}`} aria-hidden="true"></i></span>
            <div>
              <strong>{check.title}</strong>
              <small>{check.description}</small>
            </div>
          </article>
        {/each}
      </div>
    </section>

    {#if actionError}
      <InlineAlert tone="error">{actionError}</InlineAlert>
    {/if}
  </div>

  <svelte:fragment slot="footer-start">
    <div class="identity-edit-footer-state">
      <strong>{canSave ? t('Unsaved changes') : t('No unsaved changes')}</strong>
      <span class={probeResult?.ok === false ? 'is-error' : 'is-success'}>
        <i class="bi bi-circle-fill" aria-hidden="true"></i>
        {checkedLabel}
      </span>
    </div>
  </svelte:fragment>
  <svelte:fragment slot="footer">
    <div class="identity-edit-drawer-footer">
      <button type="button" class="b2s-btn b2s-btn-ghost" on:click={onClose} disabled={saving || probeRunning}>{t('Cancel')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={handleTestConnection} disabled={saving || probeRunning}>
        {probeRunning ? t('Testing…') : t('Test connection')}
      </button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={handleSave} disabled={saving || !canSave || probeRunning}>
        {saving ? t('Saving…') : t('Save changes')}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

<style>
  .identity-edit-shell {
    color: var(--b2s-color-heading);
  }

  .identity-edit-accounts {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .identity-edit-tested,
  .identity-edit-note,
  .identity-edit-drawer-footer,
  .identity-edit-footer-state span {
    display: flex;
    align-items: center;
  }

  .identity-edit-summary,
  .identity-edit-card {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
  }

  .identity-edit-summary {
    min-height: 66px;
    display: grid;
    grid-template-columns: 1fr 1.35fr 1fr 1fr;
    align-items: center;
    gap: 16px;
    padding: 13px 16px;
    margin-bottom: 10px;
  }

  .identity-edit-summary span {
    display: block;
    margin-bottom: 5px;
    color: #536885;
    font-size: var(--b2s-fs-xs);
    font-weight: 650;
  }

  .identity-edit-summary strong {
    display: block;
    min-width: 0;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-sm);
    font-weight: 650;
    overflow-wrap: anywhere;
  }

  .identity-edit-status {
    display: inline-flex !important;
    align-items: center;
    gap: 6px;
  }

  .identity-edit-status i,
  .identity-edit-tested i {
    font-size: 0.48rem;
  }

  .identity-edit-status.is-success,
  .identity-edit-tested.is-success {
    color: #0b8f49;
  }

  .identity-edit-status.is-error,
  .identity-edit-tested.is-error {
    color: var(--b2s-color-danger);
  }

  .identity-edit-status.is-info,
  .identity-edit-tested.is-info {
    color: var(--b2s-color-info);
  }

  .identity-edit-card {
    padding: 14px;
    margin-bottom: 10px;
  }

  .identity-edit-section-head {
    margin-bottom: 12px;
  }

  .identity-edit-section-head--inline {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }

  .identity-edit-section-head h3 {
    margin: 0 0 4px;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .identity-edit-section-head p {
    margin: 0;
    color: #596985;
    font-size: var(--b2s-fs-xs);
  }

  .identity-edit-tested {
    gap: 6px;
    color: #596985;
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
  }

  .identity-edit-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .identity-edit-field {
    display: grid;
    align-content: start;
    gap: 6px;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-xs);
    font-weight: 650;
  }

  .identity-edit-field--full {
    grid-column: 1 / -1;
  }

  .identity-edit-input {
    width: 100%;
    min-height: 38px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-sm);
  }

  .identity-edit-input {
    padding: 0 12px;
    outline: 0;
  }

  .identity-edit-input:focus {
    border-color: #8db5ff;
    box-shadow: 0 0 0 3px rgba(11, 99, 244, 0.12);
  }

  .identity-edit-input.is-invalid {
    border-color: #fca5a5;
    box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.08);
  }

  .identity-edit-input:disabled {
    color: var(--b2s-color-text-muted);
    background: var(--b2s-color-surface-soft);
  }




  .identity-edit-field .form-switch {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 38px;
    margin: 0;
    padding-left: 0;
  }

  .identity-edit-field .form-switch .form-check-input {
    margin: 0;
    float: none;
  }

  .identity-edit-field .form-switch .form-check-label {
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .identity-edit-hint {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .identity-edit-note {
    min-height: 38px;
    gap: 8px;
    padding: 0 12px;
    border: 1px solid #cfe0ff;
    border-radius: var(--b2s-radius-sm);
    background: #f7fbff;
    color: #12326b;
    font-size: var(--b2s-fs-xs);
  }

  .identity-edit-input-action {
    position: relative;
    display: flex;
    align-items: center;
  }

  .identity-edit-input-action .identity-edit-input {
    padding-right: 42px;
  }

  .identity-edit-input-action button {
    position: absolute;
    right: 6px;
    width: 30px;
    height: 30px;
    border: 0;
    border-radius: var(--b2s-radius-sm);
    background: transparent;
    color: #51637e;
  }

  .identity-edit-capabilities {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .identity-edit-capability {
    min-height: 66px;
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 11px;
    align-items: center;
    padding: 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
  }

  .identity-edit-capability-icon {
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-info-soft);
    color: #0b63f4;
    font-size: 1rem;
  }

  .identity-edit-capability strong,
  .identity-edit-capability small {
    display: block;
  }

  .identity-edit-capability strong {
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
  }

  .identity-edit-capability small {
    margin-top: 3px;
    color: #596985;
    font-size: var(--b2s-fs-xs);
    line-height: 1.25;
  }

  .identity-edit-capability input[type="checkbox"] {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-border-mid);
    position: relative;
    cursor: pointer;
    transition: background 0.16s ease;
  }

  .identity-edit-capability input[type="checkbox"]::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: var(--b2s-color-surface);
    transition: transform 0.16s ease;
  }

  .identity-edit-capability input[type="checkbox"]:checked {
    background: #08256b;
  }

  .identity-edit-capability input[type="checkbox"]:checked::after {
    transform: translateX(15px);
  }

  .identity-edit-validation {
    display: grid;
    grid-template-columns: 1.2fr 1fr 1fr 0.9fr;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    overflow: hidden;
    background: var(--b2s-color-surface-soft);
  }

  .identity-edit-validation.is-success {
    border-color: #b8e8c8;
    background: var(--b2s-color-success-soft);
  }

  .identity-edit-validation.is-error {
    border-color: var(--b2s-color-danger-border);
    background: #fff5f5;
  }

  .identity-edit-validation-item {
    min-height: 58px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px;
    align-items: center;
    padding: 10px 12px;
    border-right: 1px solid rgba(15, 23, 42, 0.1);
  }

  .identity-edit-validation-item:last-child {
    border-right: 0;
  }

  .identity-edit-validation-item > span {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--b2s-color-border-soft);
    color: var(--b2s-color-text-muted);
  }

  .identity-edit-validation-item.is-success > span {
    color: #0b8f49;
    background: var(--b2s-color-success-soft);
  }

  .identity-edit-validation-item.is-error > span {
    color: var(--b2s-color-danger);
    background: var(--b2s-color-danger-soft);
  }

  .identity-edit-validation-item strong,
  .identity-edit-validation-item small {
    display: block;
  }

  .identity-edit-validation-item strong {
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
  }

  .identity-edit-validation-item small {
    margin-top: 3px;
    color: #425473;
    font-size: var(--b2s-fs-xs);
    line-height: 1.28;
  }

  .identity-edit-footer-state {
    display: grid;
    gap: 5px;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-xs);
  }

  .identity-edit-footer-state span {
    gap: 6px;
    color: #0b8f49;
  }

  .identity-edit-footer-state span.is-error {
    color: var(--b2s-color-danger);
  }

  .identity-edit-footer-state i {
    font-size: 0.45rem;
  }

  .identity-edit-drawer-footer {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
  }
</style>
