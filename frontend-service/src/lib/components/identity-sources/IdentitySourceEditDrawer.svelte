<script lang="ts">
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
    bind_dn: '',
    bind_password_ref: '',
    bind_password: '',
    capabilities: { auth: true, import_groups: true, snapshot_enabled: false },
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
      protocol: source.protocol === 'ldap' ? 'ldap' : 'ldaps',
      host: source.host ?? '',
      port: source.port ?? defaultPort(source.protocol),
      base_dn: source.base_dn ?? '',
      bind_dn: source.bind_dn ?? '',
      bind_password_ref: source.bind_password_ref ?? '',
      bind_password: '',
      capabilities: {
        auth: source.capabilities?.auth ?? true,
        import_groups: source.capabilities?.import_groups ?? true,
        snapshot_enabled: source.capabilities?.snapshot_enabled ?? false
      },
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

  const hasChanges = (src: IdentitySourceRow | null, f: typeof form): boolean => {
    if (!src) return false;
    return (
      normalize(f.display_name) !== normalize(src.display_name ?? src.name) ||
      f.protocol !== (src.protocol || 'ldaps') ||
      normalize(f.host) !== normalize(src.host) ||
      Number(f.port) !== Number(src.port || defaultPort(src.protocol)) ||
      normalize(f.base_dn) !== normalize(src.base_dn) ||
      normalize(f.bind_dn) !== normalize(src.bind_dn) ||
      normalize(f.bind_password_ref) !== normalize(src.bind_password_ref) ||
      normalize(f.bind_password) !== '' ||
      f.capabilities.auth !== (src.capabilities?.auth ?? true) ||
      f.capabilities.import_groups !== (src.capabilities?.import_groups ?? true) ||
      f.capabilities.snapshot_enabled !== (src.capabilities?.snapshot_enabled ?? false) ||
      f.is_active !== (src.is_active ?? true)
    );
  };

  $: requiredOk = !!normalize(form.display_name) && !!normalize(form.host) && !!normalize(form.base_dn) && !!normalize(form.bind_dn);
  $: canSave = requiredOk && hasChanges(source, form);

  $: endpointLabel = (() => {
    const host = normalize(form.host || source?.host);
    const port = Number(form.port || source?.port || 0);
    return host ? `${host}${port > 0 ? `:${port}` : ''}` : '—';
  })();

  $: healthLabel = probeRunning
    ? 'Checking'
    : probeResult
      ? (probeResult.ok ? 'Healthy' : 'Unhealthy')
      : sourceCard?.healthLabel ?? 'Unknown';

  $: healthTone = probeRunning
    ? 'info'
    : probeResult
      ? (probeResult.ok ? 'success' : 'error')
      : sourceCard?.healthTone ?? 'muted';

  $: checkedLabel = (() => {
    if (probeRunning) return 'Testing now';
    const checked = probeResult?.checkedAt ?? source?.last_probe_at ?? null;
    return checked ? `Last tested ${formatRelativeTimestamp(checked)}` : 'No test yet';
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
    const notReported = 'Not reported by the latest probe.';

    return [
      {
        key: 'connection',
        title: ok ? 'Connection successful' : 'Connection failed',
        description: lastMessage || (ok ? 'The server responded successfully.' : 'The server did not validate the connection.'),
        tone: ok ? 'success' : 'error',
        icon: ok ? 'bi-check-lg' : 'bi-x-lg'
      },
      {
        key: 'bind',
        title: bindOk === true ? 'LDAP bind succeeded' : bindOk === false ? 'LDAP bind failed' : 'LDAP bind',
        description:
          bindOk === true
            ? 'The service account bind was successful.'
            : bindOk === false
              ? 'The service account bind failed.'
              : notReported,
        tone: checkTone(bindOk),
        icon: checkIcon(bindOk)
      },
      {
        key: 'certificate',
        title: !isLdaps
          ? 'TLS certificate'
          : tlsOk === true
            ? 'Server certificate valid'
            : tlsOk === false
              ? 'Server certificate invalid'
              : 'Server certificate',
        description: !isLdaps
          ? 'Not applicable for LDAP.'
          : tlsOk === true
            ? 'The server certificate is trusted and valid.'
            : tlsOk === false
              ? 'The server certificate could not be validated.'
              : notReported,
        tone: checkTone(tlsOk),
        icon: checkIcon(tlsOk)
      },
      {
        key: 'response',
        title: 'Response time',
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
    bind_dn: normalize(form.bind_dn) || null,
    bind_password_ref: normalize(form.bind_password_ref) || null,
    bind_password: normalize(form.bind_password) || null,
    capabilities: {
      auth: form.capabilities.auth,
      import_groups: form.capabilities.import_groups,
      snapshot_enabled: form.capabilities.snapshot_enabled
    },
    is_active: form.is_active
  });

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
      if (!payload.bind_password_ref && payload.bind_password) {
        const resolved = await resolveCredentials(fetch, {
          username: payload.bind_dn,
          password: payload.bind_password,
          secret_ref: null
        }, { secretName: `identity-source/${payload.protocol}/${payload.host || payload.name || 'ad'}`, mode: 'create' });
        payload.bind_password_ref = resolved.secret_ref ?? null;
        payload.bind_password = null;
      }
      await updateIdentitySource(fetch, source.id, payload as Partial<IdentitySourcePayload>);
      toast.success('Source updated.');
      const savedId = source.id;
      onClose();
      await onSaved(savedId);
    } catch (e: unknown) {
      const appError = toUiAppError(e, 'Unable to update', 'ui', {
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
        capabilities: { ...payload.capabilities, auth_mode: source.capabilities?.auth_mode ?? 'ntlm' }
      } as IdentitySourcePayload & { bind_password?: string | null });
      const firstCheck = result.checks[0] ?? null;
      probeResult = {
        ok: result.ok,
        status: result.status ?? null,
        jobId: result.job_id ?? null,
        message: normalize(firstCheck?.message) || (result.ok ? 'Probe OK' : 'Probe failed'),
        result: null,
        checkedAt: new Date().toISOString()
      };
      if (result.ok) toast.success('Connection validated.');
      else toast.error(probeResult.message);
    } catch (e: unknown) {
      const appError = toUiAppError(e, 'Connection test failed.', 'ui', {
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
  width="760px"
  showHeader={false}
  rootClass="identity-edit-drawer"
  panelClass="identity-edit-drawer__panel"
  contentClass="identity-edit-drawer__content"
  footerClass="identity-edit-drawer__footer"
  {onClose}
>
  <div class="identity-edit-shell">
    <header class="identity-edit-header">
      <div class="identity-edit-title-row">
        <span class="identity-edit-icon">
          <i class={`bi ${sourceIconClass(sourceCard)}`} aria-hidden="true"></i>
        </span>
        <div class="identity-edit-title">
          <h2>Edit identity source</h2>
          <p>{source?.display_name ?? source?.name ?? 'Identity source'}</p>
          <div class="identity-edit-badges">
            <StatusBadge
              status={form.is_active ? 'active' : 'disabled'}
              label={form.is_active ? 'Active' : 'Disabled'}
              variant={form.is_active ? 'success' : 'disabled'}
              compact={true}
            />
            {#if source?.used}
              <StatusBadge status="in-use" label="In use" variant="info" compact={true} />
            {/if}
          </div>
        </div>
      </div>
      <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-icon" aria-label="Close" on:click={onClose}>
        <i class="bi bi-x-lg" aria-hidden="true"></i>
      </button>
    </header>

    <section class="identity-edit-summary" aria-label="Identity source summary">
      <div>
        <span>Type</span>
        <strong>{sourceCard?.typeLabel ?? identitySourceTypeLabel('ad')}</strong>
      </div>
      <div>
        <span>Endpoint</span>
        <strong>{endpointLabel}</strong>
      </div>
      <div>
        <span>Status</span>
        <strong class={`identity-edit-status ${toneClass(healthTone)}`}>
          <i class="bi bi-circle-fill" aria-hidden="true"></i>
          {healthLabel}
        </strong>
      </div>
      <div>
        <span>Last sync</span>
        <strong>{lastSyncLabel(source)}</strong>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>Connection</h3>
        <p>Core settings required to validate the source.</p>
      </div>
      <div class="identity-edit-grid">
        <label class="identity-edit-field">
          <span>Display name</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.display_name)} bind:value={form.display_name} />
          {#if showErrors && !normalize(form.display_name)}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>Protocol</span>
          <div class="identity-edit-segmented" role="group" aria-label="LDAP protocol">
            <button type="button" class:active={form.protocol === 'ldap'} on:click={() => setProtocol('ldap')}>LDAP</button>
            <button type="button" class:active={form.protocol === 'ldaps'} on:click={() => setProtocol('ldaps')}>LDAPS</button>
          </div>
        </label>
        <label class="identity-edit-field">
          <span>Hostname / IP</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.host)} bind:value={form.host} />
          {#if showErrors && !normalize(form.host)}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>Port</span>
          <input class="identity-edit-input" type="number" min="1" max="65535" bind:value={form.port} />
        </label>
        <label class="identity-edit-field identity-edit-field--full">
          <span>Base DN</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.base_dn)} bind:value={form.base_dn} />
          {#if showErrors && !normalize(form.base_dn)}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        <div class="identity-edit-note identity-edit-field--full">
          <i class="bi bi-info-circle" aria-hidden="true"></i>
          {form.protocol === 'ldaps'
            ? 'LDAPS selected: port set to 636 automatically.'
            : 'LDAP selected: port set to 389 automatically.'}
        </div>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>Credentials</h3>
        <p>Service account used to bind to the directory.</p>
      </div>
      <div class="identity-edit-grid">
        <label class="identity-edit-field">
          <span>Bind DN</span>
          <input class="identity-edit-input" class:is-invalid={showErrors && !normalize(form.bind_dn)} bind:value={form.bind_dn} />
          {#if showErrors && !normalize(form.bind_dn)}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>Bind password</span>
          <div class="identity-edit-input-action">
            <input
              class="identity-edit-input"
              type={showPassword ? 'text' : 'password'}
              bind:value={form.bind_password}
              placeholder={form.bind_password_ref ? 'Stored secret unchanged' : 'AD account password'}
            />
            <button
              type="button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              on:click={() => (showPassword = !showPassword)}
            >
              <i class={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
          </div>
          <small class="identity-field-help">Stored securely in Secret Broker.</small>
        </label>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head">
        <h3>Capabilities</h3>
        <p>Enable features available for this source.</p>
      </div>
      <div class="identity-edit-capabilities">
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-person-check" aria-hidden="true"></i></span>
          <span>
            <strong>Authenticate users</strong>
            <small>Allow this source to authenticate users.</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.auth} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>
          <span>
            <strong>Import groups</strong>
            <small>Import groups from this source.</small>
          </span>
          <input type="checkbox" bind:checked={form.capabilities.import_groups} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-shield-check" aria-hidden="true"></i></span>
          <span>
            <strong>Source active</strong>
            <small>Enable this source across the system.</small>
          </span>
          <input type="checkbox" bind:checked={form.is_active} />
        </label>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head identity-edit-section-head--inline">
        <div>
          <h3>Validation</h3>
          <p>Results from the most recent connection test.</p>
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
      <div class="identity-edit-error" role="alert">{actionError}</div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="identity-edit-footer-state">
      <strong>{canSave ? 'Unsaved changes' : 'No unsaved changes'}</strong>
      <span class={probeResult?.ok === false ? 'is-error' : 'is-success'}>
        <i class="bi bi-circle-fill" aria-hidden="true"></i>
        {checkedLabel}
      </span>
    </div>
    <div class="identity-edit-drawer-footer">
      <button type="button" class="b2s-btn b2s-btn-ghost" on:click={onClose} disabled={saving || probeRunning}>Cancel</button>
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={handleTestConnection} disabled={saving || probeRunning}>
        {probeRunning ? 'Testing…' : 'Test connection'}
      </button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={handleSave} disabled={saving || !canSave || probeRunning}>
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

<style>
  .identity-edit-error {
    margin-top: 14px;
    padding: 10px 12px;
    border: 1px solid #fecaca;
    border-radius: 10px;
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
    font-size: 13px;
    font-weight: 600;
  }

  :global(.identity-edit-drawer .b2s-drawer__backdrop) {
    background: rgba(15, 23, 42, 0.46);
    backdrop-filter: blur(3px);
  }

  :global(.identity-edit-drawer__panel) {
    border-left: 1px solid #d8e2f0;
    border-radius: 8px 0 0 8px;
    box-shadow: -28px 0 64px rgba(15, 23, 42, 0.18);
  }

  :global(.identity-edit-drawer__content) {
    padding: 0;
    background: #ffffff;
  }

  :global(.identity-edit-drawer__footer) {
    min-height: 76px;
    padding: 14px 28px;
    justify-content: space-between;
    background: #ffffff;
    border-top: 1px solid #dce5f2;
  }

  .identity-edit-shell {
    min-height: 100%;
    padding: 26px 28px 18px;
    color: #071638;
  }

  .identity-edit-header,
  .identity-edit-title-row,
  .identity-edit-badges,
  .identity-edit-tested,
  .identity-edit-note,
  .identity-edit-drawer-footer,
  .identity-edit-footer-state span {
    display: flex;
    align-items: center;
  }

  .identity-edit-header {
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 22px;
  }

  .identity-edit-title-row {
    align-items: flex-start;
    gap: 14px;
    min-width: 0;
  }

  .identity-edit-icon {
    width: 56px;
    height: 56px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    background: #edf4ff;
    color: #0b63f4;
    font-size: 1.7rem;
  }

  .identity-edit-title h2 {
    margin: 0;
    color: #071638;
    font-size: 1.35rem;
    line-height: 1.1;
    font-weight: 700;
  }

  .identity-edit-title p {
    margin: 4px 0 10px;
    color: #596985;
    font-size: 0.9rem;
  }

  .identity-edit-badges {
    gap: 8px;
    flex-wrap: wrap;
  }

  .identity-edit-summary,
  .identity-edit-card {
    border: 1px solid #d9e2ef;
    border-radius: 8px;
    background: #ffffff;
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
    font-size: 0.73rem;
    font-weight: 650;
  }

  .identity-edit-summary strong {
    display: block;
    min-width: 0;
    color: #071638;
    font-size: 0.82rem;
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
    color: #dc2626;
  }

  .identity-edit-status.is-info,
  .identity-edit-tested.is-info {
    color: #2563eb;
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
    color: #071638;
    font-size: 0.94rem;
    font-weight: 700;
  }

  .identity-edit-section-head p {
    margin: 0;
    color: #596985;
    font-size: 0.78rem;
  }

  .identity-edit-tested {
    gap: 6px;
    color: #596985;
    font-size: 0.75rem;
    white-space: nowrap;
  }

  .identity-edit-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .identity-edit-field {
    display: grid;
    gap: 6px;
    color: #071638;
    font-size: 0.77rem;
    font-weight: 650;
  }

  .identity-edit-field--full {
    grid-column: 1 / -1;
  }

  .identity-edit-input,
  .identity-edit-segmented {
    width: 100%;
    min-height: 38px;
    border: 1px solid #d9e2ef;
    border-radius: 7px;
    background: #ffffff;
    color: #071638;
    font-size: 0.84rem;
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
    color: #64748b;
    background: #f8fafc;
  }

  .identity-edit-segmented {
    display: grid;
    grid-template-columns: 1fr 1fr;
    overflow: hidden;
    padding: 0;
  }

  .identity-edit-segmented button {
    border: 0;
    background: #f8fafc;
    color: #071638;
    font-size: 0.82rem;
    font-weight: 650;
  }

  .identity-edit-segmented button.active {
    background: #08256b;
    color: #ffffff;
  }

  .identity-edit-note {
    min-height: 38px;
    gap: 8px;
    padding: 0 12px;
    border: 1px solid #cfe0ff;
    border-radius: 7px;
    background: #f7fbff;
    color: #12326b;
    font-size: 0.78rem;
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
    border-radius: 6px;
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
    border: 1px solid #d9e2ef;
    border-radius: 8px;
    background: #ffffff;
  }

  .identity-edit-capability-icon {
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 7px;
    background: #eff6ff;
    color: #0b63f4;
    font-size: 1rem;
  }

  .identity-edit-capability strong,
  .identity-edit-capability small {
    display: block;
  }

  .identity-edit-capability strong {
    color: #071638;
    font-size: 0.76rem;
    font-weight: 700;
  }

  .identity-edit-capability small {
    margin-top: 3px;
    color: #596985;
    font-size: 0.68rem;
    line-height: 1.25;
  }

  .identity-edit-capability input[type="checkbox"] {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: 999px;
    background: #cbd5e1;
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
    background: #ffffff;
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
    border: 1px solid #d9e2ef;
    border-radius: 8px;
    overflow: hidden;
    background: #f8fafc;
  }

  .identity-edit-validation.is-success {
    border-color: #b8e8c8;
    background: #f0fdf4;
  }

  .identity-edit-validation.is-error {
    border-color: #fecaca;
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
    background: #e2e8f0;
    color: #64748b;
  }

  .identity-edit-validation-item.is-success > span {
    color: #0b8f49;
    background: #dcfce7;
  }

  .identity-edit-validation-item.is-error > span {
    color: #dc2626;
    background: #fee2e2;
  }

  .identity-edit-validation-item strong,
  .identity-edit-validation-item small {
    display: block;
  }

  .identity-edit-validation-item strong {
    color: #071638;
    font-size: 0.76rem;
    font-weight: 700;
  }

  .identity-edit-validation-item small {
    margin-top: 3px;
    color: #425473;
    font-size: 0.68rem;
    line-height: 1.28;
  }

  .identity-edit-footer-state {
    display: grid;
    gap: 5px;
    color: #071638;
    font-size: 0.78rem;
  }

  .identity-edit-footer-state span {
    gap: 6px;
    color: #0b8f49;
  }

  .identity-edit-footer-state span.is-error {
    color: #dc2626;
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
