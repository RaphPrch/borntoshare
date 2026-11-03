<script lang="ts">
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { getIdentityJob } from '$lib/api/identity';
  import { t } from '$lib/i18n';
  import { resolveCredentials } from '$lib/api/credentials';
  import {
    createIdentitySource,
    getIdentitySourceInternal,
    runIdentitySnapshot,
    type IdentitySourcePayload
  } from '$lib/api/identity-sources';
  import ServiceAccountOverride from '$lib/components/identity-sources/ServiceAccountOverride.svelte';
  import TlsCertificateField from '$lib/components/identity-sources/TlsCertificateField.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { notifyError, toUiAppError } from '$lib/errors';
  import { testIdentitySourceConnection } from '$lib/jobs/identity-source-test';
  import { pollJobUntilTerminal } from '$lib/jobs/polling';
  import { runProbeWithPolling } from '$lib/jobs/probe-runner';
  import { snapshotStore } from '$lib/stores/snapshot.store';
  import { formatDate } from '$lib/utils/format';
  import { isValidHostname, isValidIPv4 } from '$lib/utils/host-validate';
  import { extractSnapshotMeta, type IdentitySourceInternalMeta } from '$lib/utils/identity-sources';
  import {
    buildServiceAccountsPayload,
    domainFromBaseDn,
    draftsForCapabilities,
    emptyServiceAccountDrafts,
    serviceAccountDraftError,
    testServiceAccount,
    type ServiceAccountPurpose
  } from '$lib/utils/service-accounts';

  export let data: { existingNames: string[]; authDomains: { name: string; domain: string }[] };

  type Certificate = {
    certificate_pem: string;
    is_authority: boolean;
    subject: string;
    issuer: string;
    not_after: string;
    sha256: string;
    server_names: string[];
  };
  type CheckState = 'idle' | 'running' | 'ok' | 'warn' | 'failed';
  type SyncStep = { label: string; state: CheckState };

  // Server: filled by the analysis, and editable in the advanced options
  let host = '';
  let analysedHost = '';
  let analysis: CheckState = 'idle';
  let analysisMessage = '';
  let protocol: 'ldap' | 'ldaps' = 'ldaps';
  let port: number | null = 636;
  let flavor: 'ad' | 'openldap' = 'ad';
  let baseDn = '';
  let domain = '';
  let tlsVerify = true;
  let tlsPem = '';
  let tlsName = '';
  let certificate: Certificate | null = null;
  let showAdvanced = false;
  // Filled by the analysis, so a new analysis may replace them; what the administrator typed stays
  let trustedPem = '';
  let autoName = '';

  // Main account: the password is stored once, and only typing a new one replaces it
  let bindDn = '';
  let password = '';
  let showPassword = false;
  let bindRef: string | null = null;
  let accountTest: CheckState = 'idle';
  let accountMessage = '';
  let testedKey = '';
  let createWithoutTest = false;

  let capabilities = { snapshot_enabled: true, import_groups: true, auth: true, provisioning: false };
  let serviceAccounts = emptyServiceAccountDrafts();
  let accountResults: Partial<Record<ServiceAccountPurpose, { key: string; ok: boolean }>> = {};
  let name = '';

  let showErrors = false;
  let creating = false;
  let createError = '';
  let createdId: number | null = null;
  let syncState: CheckState = 'idle';
  let syncMessage = '';
  let syncSteps: SyncStep[] = [];

  const isIpAddress = (value: string) => isValidIPv4(value) || value.includes(':');
  const fingerprint = (value: string) => (value.match(/.{2}/g) ?? []).join(':').toUpperCase();
  const draftKey = (purpose: ServiceAccountPurpose) =>
    `${serviceAccounts[purpose].bind_dn}|${serviceAccounts[purpose].password}`;

  // A pasted address such as ldaps://dc01.example.com:636 also works
  $: hostParts = host.trim().replace(/^ldaps?:\/\//i, '').split('/')[0].split(':');
  $: cleanHost = hostParts.length === 2 ? hostParts[0] : host.trim().replace(/^ldaps?:\/\//i, '').split('/')[0];
  $: typedPort = hostParts.length === 2 ? Number(hostParts[1]) || null : null;
  $: hostValid = isValidIPv4(cleanHost) || isValidHostname(cleanHost);
  $: if (analysedHost && cleanHost !== analysedHost) forgetAnalysis();
  $: connectionKey = JSON.stringify([cleanHost, protocol, port, baseDn, bindDn, bindRef, password, tlsVerify, tlsPem, tlsName]);
  $: if (testedKey && connectionKey !== testedKey) {
    testedKey = '';
    accountTest = 'idle';
    accountMessage = '';
  }
  $: if (password && bindRef) bindRef = null;
  $: duplicateName = data.existingNames.some((other) => other.trim().toLowerCase() === name.trim().toLowerCase());
  $: draftError = serviceAccountDraftError(draftsForCapabilities(serviceAccounts, capabilities));
  $: certificatePending = Boolean(certificate) && protocol === 'ldaps' && tlsVerify && !tlsPem;
  $: effectiveDomain = (domain.trim() || domainFromBaseDn(baseDn)).toLowerCase();
  $: domainOwner = capabilities.auth && effectiveDomain ? data.authDomains.find((source) => source.domain === effectiveDomain) ?? null : null;
  $: noUse = !Object.values(capabilities).some(Boolean);
  $: dedicatedEnabled = (['snapshot', 'auth', 'provisioning'] as ServiceAccountPurpose[]).filter(
    (purpose) => serviceAccounts[purpose].dedicated && Boolean(draftsForCapabilities(serviceAccounts, capabilities)[purpose].dedicated)
  );
  $: dedicatedResults = dedicatedEnabled.map((purpose) => {
    const result = accountResults[purpose];
    return result && result.key === `${serviceAccounts[purpose].bind_dn}|${serviceAccounts[purpose].password}` ? result.ok : null;
  });
  $: anyTestFailed = accountTest === 'failed' || dedicatedResults.includes(false);
  $: allTestsPassed = accountTest === 'ok' && dedicatedResults.every((ok) => ok === true);
  $: formComplete =
    hostValid && Boolean(port) && Boolean(baseDn.trim()) && Boolean(bindDn.trim()) && Boolean(password || bindRef) &&
    Boolean(name.trim()) && !duplicateName && !draftError && !noUse && !domainOwner;
  $: canCreate = formComplete && !certificatePending && (allTestsPassed || (anyTestFailed && createWithoutTest));
  $: locked = creating || createdId !== null;

  function forgetAnalysis() {
    analysedHost = '';
    analysis = 'idle';
    analysisMessage = '';
    forgetCertificate();
  }

  function forgetCertificate() {
    certificate = null;
    if (trustedPem && tlsPem === trustedPem) {
      tlsPem = '';
      tlsName = '';
    }
    trustedPem = '';
  }

  async function analyse() {
    if (!hostValid || analysis === 'running') return;
    const target = cleanHost;
    analysis = 'running';
    analysisMessage = '';
    forgetCertificate();
    try {
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: {
          kind: 'identity-source',
          protocol: 'directory-discovery',
          scope: 'read',
          target: { host: target },
          options: { timeout_sec: 5 },
          context: { ui_origin: 'admin' }
        },
        intervalMs: 800,
        maxAttempts: 30
      });
      // The address changed meanwhile: this answer, and its certificate, are those of another server
      if (cleanHost !== target) {
        analysis = 'idle';
        if (hostValid && document.activeElement?.id !== 'source-host') void analyse();
        return;
      }
      const details = result.result?.details ?? {};
      analysedHost = target;
      if (!result.ok) {
        analysis = 'failed';
        analysisMessage = t(String(result.errorMessage ?? result.result?.message ?? 'Unable to analyse the server.'));
        showAdvanced = true;
        return;
      }
      protocol = details.protocol === 'ldap' ? 'ldap' : 'ldaps';
      port = typedPort ?? (Number(details.port) || (protocol === 'ldaps' ? 636 : 389));
      if (details.flavor) flavor = details.flavor === 'openldap' ? 'openldap' : 'ad';
      if (details.base_dn) baseDn = String(details.base_dn);
      certificate = details.certificate ?? null;
      if (!name.trim() || name === autoName) name = autoName = domainFromBaseDn(baseDn) || target;
      // Without the base, the administrator completes it by hand
      analysis = details.base_dn ? 'ok' : 'warn';
      if (!details.base_dn) showAdvanced = true;
    } catch (error) {
      if (cleanHost !== target) {
        analysis = 'idle';
        return;
      }
      analysis = 'failed';
      analysisMessage = error instanceof Error && error.message ? error.message : t('Unable to analyse the server.');
      showAdvanced = true;
    }
  }

  function onHostKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      void analyse();
    }
  }

  function trustCertificate() {
    if (!certificate) return;
    tlsPem = trustedPem = certificate.certificate_pem;
    // By IP address, the name cannot be checked without the one of the certificate
    if (isIpAddress(cleanHost) && !tlsName.trim()) tlsName = certificate.server_names[0] ?? '';
  }

  function setProtocol(value: 'ldap' | 'ldaps') {
    protocol = value;
    port = value === 'ldaps' ? 636 : 389;
  }

  const secretName = () => `identity-source/${protocol}/${cleanHost || name.trim() || 'ad'}`;

  async function storedBindRef(): Promise<string | null> {
    if (password) {
      const resolved = await resolveCredentials(
        fetch,
        { username: bindDn.trim() || null, password, secret_ref: null },
        { secretName: secretName(), mode: 'create' }
      );
      bindRef = resolved.secret_ref ?? null;
      if (bindRef) password = '';
    }
    return bindRef;
  }

  function connection() {
    return {
      type: 'ad' as const,
      name: name.trim() || cleanHost,
      protocol,
      host: cleanHost,
      port,
      base_dn: baseDn.trim(),
      tls_verify: tlsVerify,
      tls_ca_pem: tlsPem,
      tls_server_name: tlsName,
      capabilities: { ...capabilities, auth_mode: bindDn.includes('@') ? 'kerberos' : 'ntlm' }
    };
  }

  async function testAccount() {
    if (!hostValid || !bindDn.trim() || !(password || bindRef) || !baseDn.trim() || accountTest === 'running') {
      showErrors = true;
      return;
    }
    testedKey = '';
    accountTest = 'running';
    accountMessage = '';
    try {
      const ref = await storedBindRef();
      const result = await testIdentitySourceConnection(fetch, {
        ...connection(),
        bind_dn: bindDn.trim(),
        bind_password_ref: ref,
        bind_password: null
      } as Parameters<typeof testIdentitySourceConnection>[1]);
      accountTest = result.ok ? 'ok' : 'failed';
      accountMessage = result.checks[0]?.message ?? '';
    } catch (error) {
      accountTest = 'failed';
      accountMessage = error instanceof Error && error.message ? error.message : t('Unable to test the connection.');
    }
    testedKey = JSON.stringify([cleanHost, protocol, port, baseDn, bindDn, bindRef, password, tlsVerify, tlsPem, tlsName]);
  }

  async function testDedicated(purpose: ServiceAccountPurpose): Promise<boolean> {
    const key = draftKey(purpose);
    let ok = false;
    try {
      ok = await testServiceAccount(fetch, connection() as Parameters<typeof testServiceAccount>[1], serviceAccounts[purpose], {
        purpose,
        secretNameBase: secretName()
      });
    } catch {
      ok = false;
    }
    accountResults = { ...accountResults, [purpose]: { key, ok } };
    return ok;
  }

  function usageCheck(
    purpose: ServiceAccountPurpose | null,
    title: string,
    enabled: boolean,
    results: typeof accountResults,
    mainState: CheckState,
    drafts: typeof serviceAccounts
  ): { state: CheckState; title: string; detail: string } | null {
    if (!enabled) return null;
    if (purpose === 'provisioning') {
      const dedicated = drafts.provisioning.dedicated;
      return {
        state: 'warn',
        title,
        detail: dedicated
          ? t('Dedicated account. Its rights to write are checked when the first group is created.')
          : t('Main account. Its rights to write are checked when the first group is created.')
      };
    }
    if (purpose && drafts[purpose].dedicated) {
      const result = results[purpose];
      if (result && result.key === draftKey(purpose)) {
        return { state: result.ok ? 'ok' : 'failed', title, detail: result.ok ? t('Dedicated account: connection successful') : t('Dedicated account: connection refused') };
      }
      return { state: 'idle', title, detail: t('Dedicated account: not tested yet') };
    }
    return {
      state: mainState === 'ok' ? 'ok' : mainState === 'failed' ? 'failed' : 'idle',
      title,
      detail: mainState === 'ok' ? t('Main account: connection successful') : mainState === 'failed' ? t('Main account: connection refused') : t('Main account: not tested yet')
    };
  }

  $: certificateCheck = (protocol === 'ldap'
    ? { state: 'warn', title: t('Unencrypted connection'), detail: t('The password of the service account travels unencrypted.') }
    : !tlsVerify
      ? { state: 'warn', title: t('Server certificate'), detail: t('The connection is encrypted, but the identity of the server is not verified.') }
      : tlsPem
        ? { state: 'ok', title: t('Server certificate'), detail: t('Certificate trusted') }
        : certificate
          ? { state: 'warn', title: t('Server certificate'), detail: t('Compare the fingerprint, then trust the certificate.') }
          : { state: 'idle', title: t('Server certificate'), detail: analysis === 'failed' ? t('Not read: paste it in the advanced options if needed.') : t('Waiting for the analysis') }) as { state: CheckState; title: string; detail: string };

  $: checks = [
    {
      state: analysis,
      title: t('Server'),
      detail:
        analysis === 'ok' ? `${protocol.toUpperCase()}, ${t('port {port}', { port: port ?? '' })}`
        : analysis === 'warn' ? t('Base DN not found: enter it in the advanced options.')
        : analysis === 'running' ? t('Analysis in progress…')
        : analysis === 'failed' ? analysisMessage
        : t('Waiting for the address')
    },
    certificateCheck,
    {
      state: accountTest,
      title: t('Service account'),
      detail:
        accountTest === 'running' ? t('Testing…')
        : accountTest === 'idle' ? t('Not tested yet')
        : accountMessage
    },
    usageCheck('snapshot', t('Snapshot inventory'), capabilities.snapshot_enabled, accountResults, accountTest, serviceAccounts),
    usageCheck(null, t('Import groups'), capabilities.import_groups, accountResults, accountTest, serviceAccounts),
    usageCheck('auth', t('Authenticate users'), capabilities.auth, accountResults, accountTest, serviceAccounts),
    usageCheck('provisioning', t('Manage AD groups'), capabilities.provisioning, accountResults, accountTest, serviceAccounts)
  ].filter(Boolean) as { state: CheckState; title: string; detail: string }[];

  $: pendingReason =
    !hostValid ? t('Enter the address of the server.')
    : !baseDn.trim() ? t('Enter the base DN in the advanced options.')
    : certificatePending ? t('Trust the certificate of the server, or paste a PEM.')
    : !bindDn.trim() || !(password || bindRef) ? t('Enter the service account and its password.')
    : !name.trim() ? t('Enter a name for this directory.')
    : duplicateName ? t('This name already exists. Please choose another one.')
    : noUse ? t('Turn on at least one use.')
    : domainOwner ? t('“{name}” already authenticates this domain: turn off “Authenticate users”.', { name: domainOwner.name })
    : draftError ? t('Complete the dedicated accounts you turned on.')
    : anyTestFailed && !createWithoutTest ? t('Fix the failed test, or create it anyway.')
    : accountTest === 'idle' || accountTest === 'running' ? t('Test the service account to continue.')
    : dedicatedResults.includes(null) ? t('Test the dedicated accounts to continue.')
    : '';

  function setSyncStep(index: number, state: CheckState) {
    syncSteps = syncSteps.map((step, i) => (i === index ? { ...step, state } : step));
  }

  async function runFirstSync(sourceId: number) {
    syncState = 'running';
    syncMessage = '';
    syncSteps = [t('Dispatch'), t('In queue'), t('Collection'), t('Persist')].map((label) => ({ label, state: 'idle' }));
    let current = 0;
    setSyncStep(0, 'running');
    snapshotStore.setRunning(sourceId, 'Initial snapshot sync running');
    try {
      const run = await runIdentitySnapshot(fetch, sourceId, 'auto');
      setSyncStep(0, 'ok');
      setSyncStep(1, 'ok');
      current = 2;
      setSyncStep(2, 'running');
      // The job tells how it ended: the directory only records the snapshots that succeeded
      const polled = await pollJobUntilTerminal(String(run?.job_id ?? ''), {
        fetchJob: (id) => getIdentityJob(fetch, Number(id)),
        getRawStatus: (job: any) => String(job?.status ?? ''),
        getErrorMessage: (job: any) => String(job?.error?.message ?? job?.error?.code ?? '').trim() || undefined,
        intervalMs: 1500,
        maxAttempts: 40
      });
      if (polled.status === 'timeout') {
        // A large directory takes longer: the job goes on, this page simply stops waiting for it
        syncState = 'warn';
        syncMessage = t('The synchronization goes on in the background. Follow it from the list of directories.');
        return;
      }
      if (polled.status === 'error') throw new Error(t(polled.errorMessage ?? 'Unable to initialize first snapshot.'));
      setSyncStep(2, 'ok');
      setSyncStep(3, 'ok');
      const internal = (await getIdentitySourceInternal(fetch, sourceId)) as IdentitySourceInternalMeta;
      const meta = extractSnapshotMeta(internal);
      syncState = 'ok';
      syncMessage = t('{users} users and {groups} groups read.', { users: meta.users ?? 0, groups: meta.groups ?? 0 });
      snapshotStore.setSuccess(sourceId, {
        note: t('Initial snapshot persisted in database.'),
        lastRunAt: meta.at,
        lastSnapshotStatus: meta.status,
        lastSnapshotVersion: meta.version,
        lastSnapshotObjectsCount: meta.objects,
        lastSnapshotUsersCount: meta.users,
        lastSnapshotGroupsCount: meta.groups,
        lastSnapshotMembershipsCount: meta.memberships
      });
    } catch (error) {
      setSyncStep(current, 'failed');
      syncState = 'failed';
      const appError = toUiAppError(error, t('Unable to initialize first snapshot.'), 'ui', {
        action: 'identity_source_new.first_sync',
        sourceId
      });
      syncMessage = appError.message;
      snapshotStore.setError(sourceId, appError.message, appError.message);
    }
  }

  async function create() {
    if (!canCreate) {
      showErrors = true;
      return;
    }
    creating = true;
    createError = '';
    try {
      const ref = await storedBindRef();
      const service_accounts = await buildServiceAccountsPayload(
        fetch,
        draftsForCapabilities(serviceAccounts, capabilities),
        secretName()
      );
      const conn = connection();
      const snapshotOn = capabilities.snapshot_enabled;
      const payload = {
        ...conn,
        directory_flavor: flavor,
        domain_name: domain.trim() || domainFromBaseDn(baseDn) || null,
        bind_dn: bindDn.trim(),
        bind_password_ref: ref,
        bind_password: null,
        capabilities: conn.capabilities,
        auth_enabled: capabilities.auth,
        auth_priority: 100,
        is_active: true,
        service_accounts
      } as IdentitySourcePayload;
      const created: any = await createIdentitySource(fetch, payload);
      const sourceId = Number(created?.id ?? created?.source_id ?? created?.identity_source_id ?? 0);
      createdId = sourceId || -1;
      if (sourceId > 0 && snapshotOn) await runFirstSync(sourceId);
      else await goto('/admin/identity-sources');
    } catch (error) {
      const appError = toUiAppError(error, t('Creation failed'), 'ui', { action: 'identity_source_new.create' });
      createError = appError.code === 'IDENTITY_SOURCE_DOMAIN_TAKEN' ? t('Another active source already authenticates the users of this domain.') : appError.message;
      notifyError(appError);
    } finally {
      creating = false;
    }
  }

  // What was typed is lost by leaving before the creation
  beforeNavigate((navigation) => {
    if (navigation.type === 'leave' || locked || createdId !== null) return;
    if ((host.trim() || bindDn.trim() || password) && !window.confirm(t('Leave this page? What you entered will be lost.'))) {
      navigation.cancel();
    }
  });

  const USES = [
    { key: 'snapshot_enabled', title: 'Snapshot inventory', text: 'Needed to search and import users and groups of this source.' },
    { key: 'import_groups', title: 'Import groups', text: 'Import groups from this source.' },
    { key: 'auth', title: 'Authenticate users', text: 'Allow this source to authenticate users.' },
    { key: 'provisioning', title: 'Manage AD groups', text: 'Create AD groups and add members when access requests are approved.' }
  ] as const;
</script>

<section class="b2s-page b2s-page--admin new-source">
  <header class="page-head">
    <div>
      <a class="crumb" href="/admin/identity-sources"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Directories')}</a>
      <h1>{t('Connect a directory')}</h1>
      <p>{t('Give the address of the server: the rest is detected.')}</p>
    </div>
  </header>

  <div class="layout">
    <fieldset class="form" disabled={locked}>
      <section class="card">
        <div class="card-head">
          <h2>{t('Server')}</h2>
          {#if analysis === 'ok'}<StatusBadge compact variant="success" label={t('Detected')} />{/if}
          {#if analysis === 'warn'}<StatusBadge compact variant="warning" label={t('To complete')} />{/if}
        </div>

        <div class="host-row">
          <input
            id="source-host"
            class="b2s-input mono host-input"
            aria-label={t('Hostname / IP')}
            placeholder={t('dc01.example.com or 192.0.2.10')}
            bind:value={host}
            on:keydown={onHostKeydown}
            on:blur={() => { if (hostValid && cleanHost !== analysedHost) void analyse(); }}
          />
          <button type="button" class="b2s-btn b2s-btn-secondary" disabled={!hostValid || analysis === 'running'} on:click={analyse}>
            <i class={`bi ${analysis === 'running' ? 'bi-hourglass-split' : 'bi-search'}`} aria-hidden="true"></i>
            {analysis === 'running' ? t('Analysing…') : t('Analyse')}
          </button>
        </div>
        {#if cleanHost && !hostValid}<small class="field-error">{t('Invalid hostname / IP')}</small>{/if}
        {#if analysis === 'failed'}<InlineAlert tone="error">{analysisMessage}</InlineAlert>{/if}

        {#if analysis === 'ok' || analysis === 'warn'}
          <div class="found">
            <div><span>{t('Directory type')}</span><strong>{flavor === 'ad' ? 'Active Directory' : 'OpenLDAP'}</strong></div>
            <div><span>{t('Encryption')}</span><strong>{protocol.toUpperCase()}, {t('port {port}', { port: port ?? '' })}</strong></div>
            <div><span>{t('Base DN')}</span><strong class="mono">{baseDn || '—'}</strong></div>
          </div>
        {/if}

        {#if analysis === 'ok' && protocol === 'ldap'}
          <InlineAlert tone="warning">{t('LDAPS does not answer on this server. The password of the service account travels unencrypted.')}</InlineAlert>
        {/if}

        {#if certificatePending && certificate}
          <div class="cert">
            <div class="cert-copy">
              <strong>{t('Keep this certificate?')}</strong>
              <small>{t('Name: {value}', { value: certificate.subject })} · {t('Issued by: {value}', { value: certificate.issuer })} · {t('Expires on: {value}', { value: formatDate(certificate.not_after) })}</small>
              <small class="mono">SHA-256 {fingerprint(certificate.sha256)}</small>
              <small>
                {certificate.is_authority
                  ? t('This is the authority: it stays valid when the server certificate is renewed.')
                  : t('This is the server certificate: at its renewal, the connection stops until the new one is accepted here.')}
              </small>
            </div>
            <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" on:click={trustCertificate}>{t('Keep this certificate')}</button>
          </div>
        {:else if tlsPem && protocol === 'ldaps' && tlsVerify}
          <p class="trusted"><i class="bi bi-shield-check" aria-hidden="true"></i>{t('Certificate trusted')}</p>
        {/if}

        <button type="button" class="link" aria-expanded={showAdvanced} on:click={() => (showAdvanced = !showAdvanced)}>
          <i class={`bi ${showAdvanced ? 'bi-chevron-down' : 'bi-chevron-right'}`} aria-hidden="true"></i>
          {t('Advanced options')}
        </button>
        {#if showAdvanced}
          <div class="grid">
            <div class="field">
              <label for="source-flavor">{t('Directory type')}</label>
              <select id="source-flavor" class="b2s-input" bind:value={flavor}>
                <option value="ad">Active Directory</option>
                <option value="openldap">OpenLDAP</option>
              </select>
            </div>
            <div class="field">
              <label for="source-protocol">{t('Encryption')}</label>
              <select id="source-protocol" class="b2s-input" value={protocol} on:change={(e) => setProtocol(e.currentTarget.value === 'ldap' ? 'ldap' : 'ldaps')}>
                <option value="ldaps">LDAPS</option>
                <option value="ldap">LDAP</option>
              </select>
            </div>
            <div class="field">
              <label for="source-port">{t('Port')}</label>
              <input id="source-port" class="b2s-input mono" type="number" min="1" max="65535" bind:value={port} />
            </div>
            <div class="field">
              <label for="source-base">{t('Base DN')}</label>
              <input id="source-base" class="b2s-input mono" placeholder="DC=example,DC=com" bind:value={baseDn} />
            </div>
            <div class="field">
              <label for="source-domain">{t('Domain')}</label>
              <input id="source-domain" class="b2s-input mono" placeholder={domainFromBaseDn(baseDn) || 'example.com'} bind:value={domain} />
            </div>
            {#if protocol === 'ldaps'}
              <div class="field">
                <label for="source-cert-name">{t('Name in the certificate')}</label>
                <input id="source-cert-name" class="b2s-input mono" bind:value={tlsName} />
              </div>
              <label class="toggle full">
                <input class="cap-switch" type="checkbox" bind:checked={tlsVerify} />
                {t('Check the server certificate')}
              </label>
              {#if tlsVerify}
                <div class="field full">
                  <label for="source-pem">{t('Certificate authority (PEM)')}</label>
                  <TlsCertificateField id="source-pem" inputClass="b2s-input pem" hintClass="hint" bind:pem={tlsPem} bind:serverName={tlsName} {host} {port} />
                </div>
              {/if}
            {/if}
          </div>
        {/if}
      </section>

      <section class="card">
        <div class="card-head">
          <h2>{t('Service account')}</h2>
          {#if accountTest === 'ok'}<StatusBadge compact variant="success" label={t('Connection successful')} />{/if}
          {#if accountTest === 'failed'}<StatusBadge compact variant="error" label={t('Connection refused')} />{/if}
        </div>
        <div class="field">
          <label for="source-bind">{t('Account')}</label>
          <input id="source-bind" class="b2s-input mono" autocomplete="off" placeholder="CN=svc-b2s,OU=Services,DC=example,DC=com" bind:value={bindDn} />
        </div>
        <div class="field">
          <label for="source-password">{t('Password')}</label>
          <div class="host-row">
            <input
              id="source-password"
              class="b2s-input"
              type={showPassword ? 'text' : 'password'}
              autocomplete="new-password"
              placeholder={bindRef ? t('Password stored. Type to replace it.') : ''}
              bind:value={password}
            />
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-icon" aria-label={showPassword ? t('Hide') : t('Show')} on:click={() => (showPassword = !showPassword)}>
              <i class={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
            <button type="button" class="b2s-btn b2s-btn-secondary" disabled={accountTest === 'running' || certificatePending} on:click={testAccount}>
              {accountTest === 'running' ? t('Testing…') : t('Test')}
            </button>
          </div>
        </div>
        {#if accountTest === 'failed'}<InlineAlert tone="error">{accountMessage}</InlineAlert>{/if}
      </section>

      <section class="card">
        <div class="card-head"><h2>{t('Uses')}</h2></div>
        <div class="uses">
          {#each USES as use (use.key)}
            <label class="use" class:use--on={capabilities[use.key]}>
              <input class="cap-switch" type="checkbox" bind:checked={capabilities[use.key]} />
              <span><strong>{t(use.title)}</strong><small>{t(use.text)}</small></span>
            </label>
          {/each}
        </div>
        {#if capabilities.provisioning && !capabilities.import_groups}
          <InlineAlert tone="info">{t('Groups created in AD are imported automatically: enable “Import groups” to grant roles through them.')}</InlineAlert>
        {/if}
        {#if capabilities.snapshot_enabled || capabilities.auth || capabilities.provisioning}
          <div class="accounts">
            {#if capabilities.snapshot_enabled}
              <ServiceAccountOverride idPrefix="new-sa-snapshot" placeholder="svc-read@example.test" icon="bi-cloud-arrow-down" title={t('Snapshot inventory')} description={t('Read-only account that collects users, groups and memberships.')} bind:draft={serviceAccounts.snapshot} onTest={() => testDedicated('snapshot')} {showErrors} />
            {/if}
            {#if capabilities.auth}
              <ServiceAccountOverride idPrefix="new-sa-auth" placeholder="svc-auth@example.test" icon="bi-box-arrow-in-right" title={t('Authenticate users')} description={t('Read-only account that finds the user before checking the password.')} bind:draft={serviceAccounts.auth} onTest={() => testDedicated('auth')} {showErrors} />
            {/if}
            {#if capabilities.provisioning}
              <ServiceAccountOverride idPrefix="new-sa-provisioning" placeholder="svc-prov@example.test" icon="bi-people" title={t('Manage AD groups')} description={t('Account delegated on the target OUs: create groups and change their members.')} bind:draft={serviceAccounts.provisioning} onTest={() => testDedicated('provisioning')} {showErrors} />
            {/if}
          </div>
        {/if}
      </section>

      <section class="card">
        <div class="card-head"><h2>{t('Name')}</h2></div>
        <div class="field">
          <label for="source-name">{t('Display name')}</label>
          <input id="source-name" class="b2s-input" placeholder={t('AD Corp (prod)')} bind:value={name} />
          {#if duplicateName}<small class="field-error">{t('This name already exists')}</small>{/if}
        </div>
      </section>
    </fieldset>

    <aside class="panel">
      <h2>{t('Configuration status')}</h2>
      <ul class="checks">
        {#each checks as check (check.title)}
          <li>
            <span class={`dot dot--${check.state}`} aria-hidden="true">
              {#if check.state === 'ok'}<i class="bi bi-check-lg"></i>{:else if check.state === 'warn'}<i class="bi bi-exclamation-lg"></i>{:else if check.state === 'failed'}<i class="bi bi-x-lg"></i>{/if}
            </span>
            <span><strong>{check.title}</strong><small>{check.detail}</small></span>
          </li>
        {/each}
      </ul>

      {#if createdId === null}
        {#if anyTestFailed}
          <label class="toggle small">
            <input type="checkbox" bind:checked={createWithoutTest} />
            {t('Create it even though the test failed')}
          </label>
        {/if}
        <button type="button" class="b2s-btn b2s-btn-primary create" disabled={!canCreate || creating} on:click={create}>
          {creating ? t('Creating…') : t('Create the directory')}
        </button>
        {#if pendingReason}<small class="muted">{pendingReason}</small>{/if}
        {#if createError}<InlineAlert tone="error">{createError}</InlineAlert>{/if}
      {:else}
        <div class="sync">
          <strong>{t('First synchronization')}</strong>
          <ul class="checks">
            {#each syncSteps as step (step.label)}
              <li>
                <span class={`dot dot--${step.state}`} aria-hidden="true">
                  {#if step.state === 'ok'}<i class="bi bi-check-lg"></i>{:else if step.state === 'failed'}<i class="bi bi-x-lg"></i>{/if}
                </span>
                <span><strong>{step.label}</strong></span>
              </li>
            {/each}
          </ul>
          {#if syncMessage}
            <InlineAlert tone={syncState === 'failed' ? 'error' : syncState === 'warn' ? 'warning' : 'success'}>{syncMessage}</InlineAlert>
          {/if}
          {#if syncState === 'failed' && createdId > 0}
            <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => createdId && runFirstSync(createdId)}>{t('Try the synchronization again')}</button>
          {/if}
          {#if syncState !== 'running'}
            <a class="b2s-btn b2s-btn-primary create" href="/admin/identity-sources">{t('See the directories')}</a>
          {/if}
        </div>
      {/if}
    </aside>
  </div>
</section>

<style>
  .new-source { padding: var(--b2s-page-padding); }
  .page-head { margin-bottom: 20px; }
  .page-head h1 { margin: 4px 0 2px; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  .page-head p { margin: 0; color: var(--b2s-color-text-muted); }
  .crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); text-decoration: none; }
  .crumb:hover { color: var(--b2s-color-text); }

  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px; max-width: 1240px; align-items: start; }
  .form { display: flex; flex-direction: column; gap: 14px; min-width: 0; margin: 0; padding: 0; border: 0; }
  .card, .panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); box-shadow: var(--b2s-shadow-sm); }
  .card { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  .card-head { display: flex; align-items: center; gap: 10px; }
  h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; color: var(--b2s-color-heading); }

  .panel { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 14px; padding: 18px; }
  .checks { display: grid; gap: 11px; margin: 0; padding: 0; list-style: none; }
  .checks li { display: grid; grid-template-columns: 18px 1fr; gap: 9px; font-size: var(--b2s-text-sm); }
  .checks strong, .checks small { display: block; }
  .checks small, .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow-wrap: anywhere; }
  .dot { display: grid; place-items: center; width: 18px; height: 18px; margin-top: 1px; border-radius: 50%; background: var(--b2s-color-neutral-soft); font-size: 11px; }
  .dot--ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .dot--warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .dot--failed { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .dot--running { border: 2px solid var(--b2s-color-border-mid); border-top-color: var(--b2s-color-success-strong); background: none; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .dot--running { animation: none; } }
  .create { width: 100%; justify-content: center; text-decoration: none; }
  .sync { display: flex; flex-direction: column; gap: 12px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }

  .host-row { display: flex; gap: 8px; }
  .host-row :global(.b2s-input) { flex: 1; min-width: 0; }
  .host-input { height: 44px; font-size: var(--b2s-fs-md); }
  .mono { font-family: var(--b2s-font-mono); }
  .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .field label { font-size: var(--b2s-text-sm); font-weight: 500; }
  .field-error { color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .full { grid-column: 1 / -1; }
  .toggle { display: flex; align-items: center; gap: 9px; font-size: var(--b2s-text-sm); font-weight: 500; }
  .toggle.small { font-weight: 400; font-size: var(--b2s-font-micro); }
  .link { display: inline-flex; align-items: center; gap: 4px; align-self: flex-start; padding: 0; border: 0; background: none; color: var(--b2s-color-info-strong); font-size: var(--b2s-text-sm); cursor: pointer; }


  .found { display: grid; grid-template-columns: 1fr 1fr 1.4fr; gap: 8px; }
  .found div { padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-accent-soft); min-width: 0; }
  .found span { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .found strong { font-size: var(--b2s-text-sm); overflow-wrap: anywhere; }

  .cert { display: flex; align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid var(--b2s-color-warning-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft); }
  .cert-copy { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
  .cert-copy small { font-size: var(--b2s-font-micro); color: var(--b2s-color-text-muted); overflow-wrap: anywhere; }
  .trusted { display: flex; gap: 6px; margin: 0; color: var(--b2s-color-success-strong); font-size: var(--b2s-text-sm); }

  .uses { display: grid; gap: 8px; }
  .use { display: flex; align-items: center; gap: 12px; padding: 11px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); cursor: pointer; }
  .use--on { border-color: var(--b2s-accent-strong); background: var(--b2s-accent-soft); }
  .use strong, .use small { display: block; }
  .use small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .accounts { display: grid; gap: 8px; }
</style>
