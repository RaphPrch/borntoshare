<script lang="ts">
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import WizardSteps from '$lib/components/ui/WizardSteps.svelte';
  import { sleep } from '$lib/utils/values';
  import { createEventDispatcher } from 'svelte';
  import { toast } from '$lib/stores/toast';
  import RunProbeButton from '$lib/components/jobs/RunProbeButton.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { buildIdentitySourceProbeRequest } from '$lib/jobs/probe-builders';
  import { resolveCredentials } from '$lib/api/credentials';
  import { isValidHostname, isValidIPv4 } from '$lib/utils/host-validate';
  import { resolveStatusVariant } from '$lib/utils/status';
  import { notifyError, toUiAppError } from '$lib/errors';
  import type { ProbeRunRequest } from '$lib/api/probes';
  import {
    getIdentitySourceInternal,
    runIdentitySnapshot,
    type IdentitySourcePayload
  } from '$lib/api/identity-sources';
  import {
    extractSnapshotMeta,
    type IdentitySourceCreateResult,
    type IdentitySnapshotMeta,
    type IdentitySourceInternalMeta
  } from '$lib/utils/identity-sources';
  import { jobsStore } from '$lib/stores/jobs.store';
  import { snapshotStore } from '$lib/stores/snapshot.store';

  export let onTest: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<{
    ok: boolean;
    checks: Array<{ key: string; ok: boolean; message?: string }>;
    status?: string;
    job_id?: string | number;
  }>;
  export let onCreate: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<IdentitySourceCreateResult>;
  export let existingNames: string[] = [];

  const dispatch = createEventDispatcher();

  type WizardStepKey = 'type' | 'capabilities' | 'connection' | 'snapshot' | 'review';
  type WizardStepItem = { key: WizardStepKey; label: string };
  const stepsWithoutSnapshot: WizardStepItem[] = [
    { key: 'type', label: t('Select Type') },
    { key: 'capabilities', label: t('Capabilities') },
    { key: 'connection', label: t('Connection') },
    { key: 'review', label: t('Review') }
  ];
  const stepsWithSnapshot: WizardStepItem[] = [
    { key: 'type', label: t('Select Type') },
    { key: 'capabilities', label: t('Capabilities') },
    { key: 'connection', label: t('Connection') },
    { key: 'snapshot', label: t('Snapshot') },
    { key: 'review', label: t('Review') }
  ];

  let step = 1;
  let activeSteps: WizardStepItem[] = stepsWithoutSnapshot;
  let currentStepKey: WizardStepKey = 'type';
  let maxStep = 4;
  let testResult:
    | { ok: boolean; checks: { key: string; ok: boolean; message?: string }[] }
    | null = null;
  let probeStatus: 'idle' | 'running' | 'success' | 'failed' = 'idle';
  let testError: string | null = null;
  let createError: string | null = null;
  let creating = false;
  let createDone = false;
  let createdSourceId: number | null = null;
  // Set while the "Initialize snapshot" button creates the source: it starts the snapshot itself.
  let snapshotStartedByCaller = false;
  let snapshotCountNote: string | null = null;
  let lastSnapshotAt: string | null = null;
  let lastSnapshotStatus: string | null = null;
  let lastSnapshotVersion: number | null = null;
  let lastSnapshotObjectsCount: number | null = null;
  let lastSnapshotUsersCount: number | null = null;
  let lastSnapshotGroupsCount: number | null = null;
  let lastSnapshotMembershipsCount: number | null = null;
  let loadingSnapshotCount = false;
  type SnapshotInitState = 'idle' | 'running' | 'success' | 'failed';
  type SnapshotInitStepState = 'pending' | 'running' | 'done' | 'error';
  type SnapshotInitStep = {
    key: 'dispatch' | 'queued' | 'collect' | 'persist';
    label: string;
    description: string;
    state: SnapshotInitStepState;
  };

  const createSnapshotInitSteps = (): SnapshotInitStep[] => [
    {
      key: 'dispatch',
      label: t('Dispatch'),
      description: t('Request sent to orchestrator'),
      state: 'pending'
    },
    {
      key: 'queued',
      label: t('Queue'),
      description: t('Job scheduled on backend'),
      state: 'pending'
    },
    {
      key: 'collect',
      label: t('Collecte'),
      description: t('Collecte LDAP et projection snapshot'),
      state: 'pending'
    },
    {
      key: 'persist',
      label: t('Persist'),
      description: t('Date/version/accounts persisted in DB'),
      state: 'pending'
    }
  ];

  let snapshotInitState: SnapshotInitState = 'idle';
  let snapshotInitProgress = 0;
  let snapshotInitError: string | null = null;
  let snapshotInitStatusText: string | null = null;
  let snapshotInitSteps: SnapshotInitStep[] = createSnapshotInitSteps();
  type SnapshotTestSummaryStatus = 'not run' | 'success' | 'failed';
  let snapshotTestSummaryStatus: SnapshotTestSummaryStatus = 'not run';
  let probeSummaryStatus: SnapshotTestSummaryStatus = 'not run';
  let snapshotEnabledSummary = true;
  let firstSnapshotAutomaticSummary = false;
  let showStep3Errors = false;

  let adHostInput = '';
  let resolveHint: { ok: boolean; message: string } | null = null;
  let showBindPassword = false;

  // LDAPS-only (UI-only) advanced settings

  /**
   * 🔐 UI ONLY — never persisted, never sent directly
   */
  let uiBindPassword = '';

  const payload: IdentitySourcePayload = {
    type: 'ad',
    name: '',
    protocol: 'ldap',
    host: '',
    port: 389,
    base_dn: '',
    bind_dn: '',
    bind_password_ref: null,
    capabilities: { auth: true, import_groups: true, snapshot_enabled: false, auth_mode: 'ntlm' },
    is_active: true
  };

  let protocolChoice: 'ldap' | 'ldaps' = payload.protocol ?? 'ldap';

  $: isKerberosAuth = (payload.bind_dn ?? '').includes('@');
  $: isNtlmAuth = !!payload.bind_dn && !isKerberosAuth;

  function selectType(value: IdentitySourcePayload['type']) {
    payload.type = value;
  }

  function setProtocol(value: 'ldap' | 'ldaps') {
    protocolChoice = value;
    payload.protocol = value;
    payload.port = value === 'ldaps' ? 636 : 389;
  }

  function resolveName(): string {
    if (payload.name?.trim()) return payload.name.trim();
    return (payload.host || adHostInput || 'ad-source').trim();
  }

  function normalizePayload(): IdentitySourcePayload & { _secret?: string } {
    const host = (payload.host || adHostInput || '').trim() || null;
    const bindDn = payload.bind_dn?.trim() || null;
    const authEnabled = Boolean(payload.capabilities?.auth);
    const normalizedCapabilities = {
      ...payload.capabilities,
      auth_mode: bindDn?.includes('@') ? 'kerberos' : 'ntlm'
    } as NonNullable<IdentitySourcePayload['capabilities']>;

    if (payload.capabilities?.snapshot_enabled === true) {
      normalizedCapabilities.snapshot_enabled = true;
    } else {
      delete normalizedCapabilities.snapshot_enabled;
    }

    return {
      ...payload,
      name: resolveName(),
      host,
      port: payload.port ?? null,
      base_dn: payload.base_dn?.trim() || null,
      bind_dn: bindDn,
      bind_password_ref: payload.bind_password_ref || null,
      capabilities: normalizedCapabilities,
      auth_enabled: authEnabled,
      auth_priority: 100,
      /**
       * 🔐 INTERNAL ONLY
       * Used ONLY by onTest / onCreate to request a backend-managed secret_ref.
       */
      _secret: uiBindPassword || undefined
    };
  }

  function next() {
    if ((currentStepKey === 'type' || currentStepKey === 'connection') && isDuplicateSourceName()) {
      toast.error(t('This name already exists. Please choose another one.'));
      return;
    }
    if (currentStepKey === 'connection' && !canContinueStep3) {
      showStep3Errors = true;
      return;
    }
    if (step < maxStep) step += 1;
  }

  function isDuplicateSourceName(): boolean {
    const candidate = String(payload.name ?? '').trim().toLowerCase();
    if (!candidate) return false;
    return (existingNames ?? []).some((n) => String(n ?? '').trim().toLowerCase() === candidate);
  }

  function back() {
    if (creating) return;
    if (step > 1) step -= 1;
    showStep3Errors = false;
  }

  function updateSnapshotInitStep(key: SnapshotInitStep['key'], state: SnapshotInitStepState) {
    snapshotInitSteps = snapshotInitSteps.map((step) =>
      step.key === key ? { ...step, state } : step
    );
  }

  function failSnapshotInitRunningStep() {
    const running = snapshotInitSteps.find((step) => step.state === 'running');
    if (!running) return;
    updateSnapshotInitStep(running.key, 'error');
  }

  function resetSnapshotInitUi() {
    snapshotInitState = 'idle';
    snapshotInitProgress = 0;
    snapshotInitError = null;
    snapshotInitStatusText = null;
    snapshotInitSteps = createSnapshotInitSteps();
  }

  const snapshotStatusLabel = (status?: string | null): string =>
    String(status ?? '').trim() || 'unknown';

  const snapshotStatusVariant = (status?: string | null) =>
    resolveStatusVariant(snapshotStatusLabel(status));

  const snapshotTestStatusVariant = (status: SnapshotTestSummaryStatus) => {
    if (status === 'success') return 'success';
    if (status === 'failed') return 'error';
    return 'muted';
  };

  function formatSnapshotDate(value?: string | null): string {
    if (!value) return '—';
    const parsed = new Date(value);
    if (!Number.isFinite(parsed.getTime())) return String(value);
    return parsed.toLocaleString();
  }

  async function fetchSnapshotMeta(sourceId: number): Promise<IdentitySnapshotMeta> {
    const internal = (await getIdentitySourceInternal(fetch, sourceId)) as IdentitySourceInternalMeta;
    return extractSnapshotMeta(internal);
  }

  const probeWizardJobInput = () => ({
    entityType: 'identity-source-wizard',
    entityId: String(payload.host ?? resolveName() ?? 'new'),
    action: 'probe'
  } as const);

  const snapshotJobInput = (sourceId: number) => ({
    entityType: 'identity-source',
    entityId: sourceId,
    action: 'snapshot'
  } as const);

  async function loadSnapshotCounts(sourceId: number): Promise<void> {
    loadingSnapshotCount = true;
    snapshotCountNote = null;
    snapshotStore.setRunning(sourceId, 'Loading snapshot metadata');
    try {
      for (let i = 0; i < 6; i += 1) {
        const meta = await fetchSnapshotMeta(sourceId);
        const objects = meta.objects;
        const users = meta.users;
        const groups = meta.groups;
        const memberships = meta.memberships;
        const derived = objects ?? ((users !== null || groups !== null) ? (users ?? 0) + (groups ?? 0) : null);

        if (meta.at) lastSnapshotAt = meta.at;
        if (meta.status) lastSnapshotStatus = meta.status;
        if (meta.version !== null) lastSnapshotVersion = meta.version;

        if (derived !== null) {
          lastSnapshotObjectsCount = derived;
          lastSnapshotUsersCount = users;
          lastSnapshotGroupsCount = groups;
          lastSnapshotMembershipsCount = memberships;
          snapshotStore.setSuccess(sourceId, {
            note: t('Snapshot metadata loaded'),
            lastRunAt: meta.at,
            lastSnapshotStatus: meta.status,
            lastSnapshotVersion: meta.version,
            lastSnapshotObjectsCount: derived,
            lastSnapshotUsersCount: users,
            lastSnapshotGroupsCount: groups,
            lastSnapshotMembershipsCount: memberships
          });
          return;
        }

        if (i < 5) await sleep(900);
      }

      lastSnapshotObjectsCount = 0;
      lastSnapshotUsersCount = 0;
      lastSnapshotGroupsCount = 0;
      lastSnapshotMembershipsCount = 0;
      snapshotCountNote = 'No active snapshot detected at the moment.';
      snapshotStore.setSuccess(sourceId, {
        note: snapshotCountNote,
        lastRunAt: lastSnapshotAt,
        lastSnapshotStatus,
        lastSnapshotVersion,
        lastSnapshotObjectsCount: 0,
        lastSnapshotUsersCount: 0,
        lastSnapshotGroupsCount: 0,
        lastSnapshotMembershipsCount: 0
      });
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Lecture du snapshot impossible.'), 'ui', {
        action: 'identity_sources_wizard.load_snapshot_counts',
        sourceId
      });
      lastSnapshotObjectsCount = null;
      lastSnapshotUsersCount = null;
      lastSnapshotGroupsCount = null;
      lastSnapshotMembershipsCount = null;
      snapshotCountNote = appError.message;
      snapshotStore.setError(sourceId, appError.message, snapshotCountNote);
      notifyError(appError);
    } finally {
      loadingSnapshotCount = false;
    }
  }

  async function startInitialSnapshotSync() {
    if (snapshotInitState === 'running' || creating) return;

    if (!createdSourceId) {
      if (createDone) {
        snapshotInitError = 'Source created, but identifier not found to start synchronization.';
        snapshotInitStatusText = t('Snapshot initialization failed.');
        return;
      }

      snapshotStartedByCaller = true;
      try {
        await finish();
      } finally {
        snapshotStartedByCaller = false;
      }
      if (!createdSourceId) {
        snapshotInitError = createError ?? t('Unable to create source before snapshot initialization.');
        snapshotInitStatusText = t('Snapshot initialization failed.');
        return;
      }
    }

    jobsStore.startJob(snapshotJobInput(Number(createdSourceId)), {
      message: t('Snapshot sync running')
    });
    snapshotStore.setRunning(Number(createdSourceId), 'Initial snapshot sync running');

    snapshotInitState = 'running';
    snapshotInitProgress = 6;
    snapshotInitError = null;
    snapshotInitStatusText = t('Dispatching snapshot request…');
    snapshotInitSteps = createSnapshotInitSteps();
    updateSnapshotInitStep('dispatch', 'running');

    try {
      const run = await runIdentitySnapshot(fetch, Number(createdSourceId), 'auto');
      updateSnapshotInitStep('dispatch', 'done');
      snapshotInitProgress = 22;

      updateSnapshotInitStep('queued', 'running');
      snapshotInitStatusText = `Snapshot queued${run?.job_id ? ` · job #${run.job_id}` : ''}`;
      await sleep(280);
      updateSnapshotInitStep('queued', 'done');
      snapshotInitProgress = 36;

      updateSnapshotInitStep('collect', 'running');
      let finalized = false;

      for (let i = 0; i < 40; i += 1) {
        const meta = await fetchSnapshotMeta(Number(createdSourceId));
        if (meta.at) lastSnapshotAt = meta.at;
        if (meta.status) lastSnapshotStatus = meta.status;
        if (meta.version !== null) lastSnapshotVersion = meta.version;

        const normalized = String(meta.status ?? '').trim().toUpperCase();
        if (normalized) snapshotInitStatusText = t('Snapshot status: {normalized}', { normalized });

        snapshotInitProgress = Math.min(84, 42 + i * 1.1);

        if (['FAILED', 'ERROR', 'CANCELED', 'CANCELLED'].includes(normalized)) {
          throw new Error(t('Snapshot {toLowerCase}.', { toLowerCase: normalized.toLowerCase() }));
        }

        const hasPersistedMetadata = Boolean(meta.at) || (meta.version ?? 0) > 0;
        const successStatus = ['ACTIVE', 'SUCCEEDED'].includes(normalized);
        if (hasPersistedMetadata && (successStatus || i >= 2)) {
          finalized = true;
          break;
        }

        await sleep(1500);
      }

      if (!finalized) {
        throw new Error('Snapshot still running. Check status in a few moments.');
      }

      updateSnapshotInitStep('collect', 'done');
      updateSnapshotInitStep('persist', 'running');
      snapshotInitProgress = 90;
      snapshotInitStatusText = t('Refreshing persisted metadata…');

      await loadSnapshotCounts(Number(createdSourceId));

      updateSnapshotInitStep('persist', 'done');
      snapshotInitProgress = 100;
      snapshotInitState = 'success';
      snapshotInitStatusText = t('Initial snapshot persisted in database.');
      jobsStore.succeedJob(snapshotJobInput(Number(createdSourceId)), {
        message: t('Initial snapshot persisted'),
        summary: {
          status: lastSnapshotStatus,
          version: lastSnapshotVersion,
          objects: lastSnapshotObjectsCount,
          users: lastSnapshotUsersCount,
          groups: lastSnapshotGroupsCount,
          memberships: lastSnapshotMembershipsCount
        }
      });
      snapshotStore.setSuccess(Number(createdSourceId), {
        note: snapshotInitStatusText,
        lastRunAt: lastSnapshotAt,
        lastSnapshotStatus,
        lastSnapshotVersion,
        lastSnapshotObjectsCount,
        lastSnapshotUsersCount,
        lastSnapshotGroupsCount,
        lastSnapshotMembershipsCount
      });
      toast.success(t('Snapshot synchronized.'));
    } catch (e: unknown) {
      failSnapshotInitRunningStep();
      snapshotInitState = 'failed';
      snapshotInitProgress = Math.max(snapshotInitProgress, 34);
      const appError = toUiAppError(e, t('Unable to initialize first snapshot.'), 'ui', {
        action: 'identity_sources_wizard.start_initial_snapshot_sync',
        sourceId: createdSourceId
      });
      snapshotInitError = appError.message;
      snapshotInitStatusText = t('Snapshot initialization failed.');
      jobsStore.failJob(snapshotJobInput(Number(createdSourceId)), {
        message: snapshotInitError,
        error: snapshotInitError
      });
      snapshotStore.setError(Number(createdSourceId), snapshotInitError, snapshotInitStatusText);
      notifyError(appError);
    }
  }

  async function finish() {
    if (creating) return;
    if (createDone) {
      dispatch('done');
      return;
    }

    creating = true;
    createError = null;
    snapshotCountNote = null;
    createdSourceId = null;
    lastSnapshotAt = null;
    lastSnapshotStatus = null;
    lastSnapshotVersion = null;
    lastSnapshotObjectsCount = null;
    lastSnapshotUsersCount = null;
    lastSnapshotGroupsCount = null;
    lastSnapshotMembershipsCount = null;
    resetSnapshotInitUi();
    try {
      const created = await onCreate(normalizePayload());

      const sourceId = Number(created?.id ?? created?.source_id ?? created?.identity_source_id ?? 0);
      if (Number.isFinite(sourceId) && sourceId > 0) {
        createdSourceId = sourceId;
        snapshotStore.upsert(sourceId, {
          note: t('Identity source created from wizard')
        });
        await loadSnapshotCounts(sourceId);
        // Initial snapshot for AD sources with snapshots enabled (best effort).
        if (!snapshotStartedByCaller && payload.type === 'ad' && snapshotEnabledSummary) {
          runIdentitySnapshot(fetch, sourceId, 'auto').catch(() => undefined);
        }
      }
      createDone = true;
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Creation failed'), 'ui', {
        action: 'identity_sources_wizard.finish_create'
      });
      createError = appError.message;
      notifyError(appError);
    } finally {
      creating = false;
    }
  }

  function resolveHostInput() {
    const value = adHostInput.trim();
    if (!value) {
      resolveHint = { ok: false, message: t('Enter a hostname or an IP.') };
      return;
    }
    if (isValidIPv4(value)) {
      resolveHint = { ok: true, message: t('Valid IP.') };
      return;
    }
    if (isValidHostname(value)) {
      resolveHint = { ok: true, message: t('Valid hostname.') };
      return;
    }
    resolveHint = { ok: false, message: t('Invalid hostname/IP format.') };
  }

  function resolveProbeHost(): string | null {
    const value = (payload.host || adHostInput || '').trim();
    if (!value) return null;
    if (isValidIPv4(value) || isValidHostname(value)) return value;
    return null;
  }

  async function ensureBindSecretRef(): Promise<string | null> {
    const protocol = String(payload.protocol ?? protocolChoice ?? 'ldap').toLowerCase() === 'ldap' ? 'ldap' : 'ldaps';
    const bindSecret = String(uiBindPassword ?? '').trim();

    if (!payload.bind_password_ref && bindSecret) {
      const resolved = await resolveCredentials(fetch, {
        username: payload.bind_dn ?? null,
        password: bindSecret,
        secret_ref: payload.bind_password_ref ?? null
      }, {
        secretName: `identity-source/${protocol}/${payload.host || adHostInput || payload.name || 'ad'}`,
        mode: 'create'
      });

      payload.bind_password_ref = resolved.secret_ref ?? payload.bind_password_ref ?? null;
      if (payload.bind_password_ref) {
        uiBindPassword = '';
      }
    }

    return payload.bind_password_ref ?? null;
  }

  function buildWizardProbeRequest(secretRef: string | null = payload.bind_password_ref ?? null): ProbeRunRequest | null {
    const host = resolveProbeHost();
    const protocol = String(payload.protocol ?? protocolChoice ?? 'ldap').toLowerCase() === 'ldap' ? 'ldap' : 'ldaps';
    if (!host) return null;
    const authMode = payload.bind_dn?.includes('@') ? 'kerberos' : 'ntlm';
    return buildIdentitySourceProbeRequest({
      protocol,
      host,
      port: payload.port,
      baseDn: payload.base_dn,
      bindDn: payload.bind_dn,
      secretRef,
      authMode,
      uiOrigin: 'wizard'
    });
  }

  $: canContinueStep3 =
    !!payload.name?.trim() &&
    !!(payload.host || adHostInput) &&
    !!payload.port &&
    !!payload.base_dn &&
    !!payload.bind_dn &&
    !!(uiBindPassword || payload.bind_password_ref) &&
    (!adHostInput || isValidIPv4(adHostInput) || isValidHostname(adHostInput)) &&
    !isDuplicateSourceName();

  // If user starts typing a new bind password, force regeneration of secret_ref
  // so the newly entered value is used instead of a previously resolved ref.
  $: if (uiBindPassword && payload.bind_password_ref) {
    payload.bind_password_ref = null;
  }

  $: snapshotEnabledSummary = payload.capabilities?.snapshot_enabled === true;
  $: firstSnapshotAutomaticSummary = snapshotEnabledSummary;
  $: activeSteps = snapshotEnabledSummary ? stepsWithSnapshot : stepsWithoutSnapshot;
  $: maxStep = activeSteps.length;
  $: if (step > maxStep) step = maxStep;
  $: currentStepKey = activeSteps[Math.max(0, step - 1)]?.key ?? 'type';
  $: snapshotTestSummaryStatus =
    snapshotInitState === 'success'
      ? 'success'
      : snapshotInitState === 'failed'
        ? 'failed'
        : 'not run';
  $: probeSummaryStatus =
    testResult
      ? (testResult.ok ? 'success' : 'failed')
      : probeStatus === 'success'
        ? 'success'
        : probeStatus === 'failed'
          ? 'failed'
          : 'not run';

  $: canContinue =
    (currentStepKey === 'type' && !!payload.type) ||
    currentStepKey === 'capabilities' ||
    (currentStepKey === 'connection' && canContinueStep3) ||
    currentStepKey === 'snapshot' ||
    currentStepKey === 'review';
</script>

<div class="is-wizard b2s-wizard is-wizard--modal" class:is-wizard--ldaps={protocolChoice === 'ldaps'}>
  <div class="is-wizard-shell">
    <div class="is-wizard-header">
      <h1 id="identity-sources-wizard-title">{t('Connect Identity Source')}</h1>
      <p>{t('Configure Active Directory (LDAP) to import identities.')}</p>
    </div>

    <WizardSteps steps={activeSteps.map((s) => ({ label: s.label }))} current={step} />

    <div class="is-card">
      {#if currentStepKey === 'type'}
        <h2>{t('Select Type')}</h2>

        <div class="field">
          <label for="identity-source-name">{t('Name')}</label>
          <input
            id="identity-source-name"
            bind:value={payload.name}
            placeholder={t('AD Corp (prod)')}
            autocomplete="off"
          />
        </div>

        <div class="cards">
          <button type="button" class="card" class:selected={payload.type === 'ad'} on:click={() => selectType('ad')}>
            <div class="card__icon"><i class="bi bi-diagram-3"></i></div>
            <div class="card__title">{t('Active Directory / LDAP')}</div>
            <div class="card__desc">{t('LDAP server for Microsoft Active Directory or generic LDAP')}</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title={t('Coming soon')}
          >
            <div class="card__icon"><i class="bi bi-key"></i></div>
            <div class="card__title">{t('OIDC / SCIM 2.0')}</div>
            <div class="card__desc">{t('Provision identities via OIDC / SCIM')}</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title={t('Coming soon')}
          >
            <div class="card__icon"><i class="bi bi-cloud"></i></div>
            <div class="card__title">{t('Azure AD')}</div>
            <div class="card__desc">{t('Microsoft Entra ID connector')}</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title={t('Coming soon')}
          >
            <div class="card__icon"><i class="bi bi-amazon"></i></div>
            <div class="card__title">{t('Amazon IAM')}</div>
            <div class="card__desc">{t('AWS identity source')}</div>
          </button>
        </div>
      {/if}

      {#if currentStepKey === 'capabilities'}
        <div class="capabilities">
          <div class="capabilities-head">
            <h2>{t('Capabilities')}</h2>
            <p class="capabilities-sub">{t('Enable features available for this source.')}</p>
          </div>

          <div class="cap-card">
            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-person-check" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>{t('Authenticate users')}</strong>
                <small>{t('Allow this source to authenticate users.')}</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.auth} />
            </label>

            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>{t('Import groups')}</strong>
                <small>{t('Import groups from this source.')}</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.import_groups} />
            </label>

            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-cloud-arrow-down" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>{t('Snapshot inventory')}</strong>
                <small>{t('Synchronize directory inventory and health metadata.')}</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.snapshot_enabled} />
            </label>
          </div>

          {#if payload.capabilities.snapshot_enabled}
            <div class="hint ok">{t('Snapshot inventory will add one additional configuration step.')}</div>
          {/if}
        </div>
      {/if}

      {#if currentStepKey === 'connection'}
      <h2>{t('Connection')}</h2>
      <p class="step-hint">{t('Provide LDAP/LDAPS parameters. Fields marked “Required” must be filled in.')}</p>
      {#if payload.type === 'ad'}
        <div class="grid">
            <div class="field field--full">
              <label for="identity-source-name-step3">{t('Name')}</label>
              <input
                id="identity-source-name-step3"
                bind:value={payload.name}
                placeholder={t('AD Corp (prod)')}
                autocomplete="off"
              />
              {#if showStep3Errors && !payload.name?.trim()}
                <FieldError>{t('Required')}</FieldError>
              {:else if showStep3Errors && isDuplicateSourceName()}
                <FieldError>{t('This name already exists')}</FieldError>
              {/if}
            </div>

            <div class="field">
              <label for="identity-source-host">{t('Hostname / IP')}</label>
              <div class="b2s-input-with-action">
                <input
                  id="identity-source-host"
                  bind:value={adHostInput}
                  placeholder={t('dc1.corp.local or 192.168.10.10')}
                />
                <button
                  class="b2s-input-action"
                  type="button"
                  aria-label={t('Resolve host')}
                  on:click={resolveHostInput}
                >
                  <i class="bi bi-search" aria-hidden="true"></i>
                </button>
              </div>
              {#if showStep3Errors && !adHostInput}
                <FieldError>{t('Required')}</FieldError>
              {:else if showStep3Errors && adHostInput && !isValidIPv4(adHostInput) && !isValidHostname(adHostInput)}
                <FieldError>{t('Invalid hostname / IP')}</FieldError>
              {/if}
              {#if resolveHint}
                <span class={resolveHint.ok ? 'hint ok' : 'hint'}>{resolveHint.message}</span>
              {/if}
            </div>
            <div class="field">
              <label>{t('Protocol')}</label>
              <div class="protocol-switch">
                <button
                  type="button"
                  class="protocol-btn"
                  class:active={protocolChoice === 'ldap'}
                  on:click={() => setProtocol('ldap')}
                >
                  LDAP
                </button>
                <button
                  type="button"
                  class="protocol-btn"
                  class:active={protocolChoice === 'ldaps'}
                  on:click={() => setProtocol('ldaps')}
                >
                  LDAPS
                </button>
              </div>
            </div>
            <div class="field">
              <label for="identity-source-port">{t('Port')}</label>
              <input
                id="identity-source-port"
                type="number"
                bind:value={payload.port}
              />
              {#if showStep3Errors && !payload.port}
                <FieldError>{t('Required')}</FieldError>
              {/if}
            </div>
            <div class="field">
              <label for="identity-source-base-dn">{t('Base DN')}</label>
              <input
                id="identity-source-base-dn"
                bind:value={payload.base_dn}
                placeholder="DC=corp,DC=local"
              />
              {#if showStep3Errors && !payload.base_dn}
                <FieldError>{t('Required')}</FieldError>
              {/if}
            </div>
            <div class="field">
              <label for="identity-source-bind-dn">{t('Bind DN')}</label>
              <input
                id="identity-source-bind-dn"
                bind:value={payload.bind_dn}
                placeholder="svc_ad_bind"
              />
              {#if showStep3Errors && !payload.bind_dn}
                <FieldError>{t('Required')}</FieldError>
              {/if}
            </div>

            <div class="field">
              <label for="identity-source-bind-password">{t('Bind password')}</label>
              <div class="b2s-input-with-action">
                <input
                  id="identity-source-bind-password"
                  type={showBindPassword ? 'text' : 'password'}
                  bind:value={uiBindPassword}
                  autocomplete="new-password"
                />
                <button
                  class="b2s-input-action"
                  type="button"
                  aria-label={showBindPassword ? t('Hide password') : t('Show password')}
                  on:click={() => (showBindPassword = !showBindPassword)}
                >
                  <i class={`bi ${showBindPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
                </button>
              </div>
              {#if showStep3Errors && !uiBindPassword && !payload.bind_password_ref}
                <FieldError>{t('Required')}</FieldError>
              {/if}
            </div>

            <div class="field field--full">
              {#if isNtlmAuth}
                <span class="hint">{t('⚠️ In hardened environments (CIS), Kerberos is recommended. Suggested format: user@realm.')}</span>
              {/if}
              {#if isKerberosAuth}
                <span class="hint ok">{t('Kerberos detected. Prerequisites: DNS SRV Kerberos, synchronized NTP, ports 88/464 open, krb5.conf mounted in the runner.')}</span>
              {/if}
            </div>
          </div>
        {/if}

        <div class="test-actions">
          <RunProbeButton
            fetchFn={fetch}
            requestFactory={async () => {
              const secretRef = await ensureBindSecretRef();
              return buildWizardProbeRequest(secretRef);
            }}
            label={t('Run Probe')}
            busyLabel={t('Running probe…')}
            fullWidth={true}
            showIcon={true}
            iconClass="bi bi-activity"
            busyIconClass="bi bi-hourglass-split"
            buttonClass={`se-run-probe-btn b2s-btn b2s-btn-secondary ${probeStatus === 'success' ? 'is-success' : ''}`}
            hideSuccessPanel={true}
            disabled={!canContinueStep3}
            beforeRun={async () => {
              probeStatus = 'running';
              showStep3Errors = false;
              testError = null;
              jobsStore.startJob(probeWizardJobInput(), {
                message: t('Probe running')
              });
              if (!canContinueStep3) {
                showStep3Errors = true;
                throw new Error(t('Complete the required connection fields first.'));
              }
              const secretRef = await ensureBindSecretRef();
              if (!secretRef && payload.bind_dn?.trim()) {
                throw new Error(t('Password is required to test the connection (no secret_ref available).'));
              }
            }}
            on:done={(e) => {
              const ok = Boolean(e.detail.ok);
              const message = ok
                ? t('Probe OK')
                : (e.detail.error?.message ?? t('Probe failed'));

              probeStatus = ok ? 'success' : 'failed';

              testResult = {
                ok,
                checks: [{ key: 'probe', ok, message }]
              };
              testError = ok ? null : message;

              if (ok) {
                jobsStore.succeedJob(probeWizardJobInput(), {
                  message: t('Probe OK'),
                  summary: { message }
                });
              } else {
                jobsStore.failJob(probeWizardJobInput(), {
                  message,
                  error: message
                });
              }

              if (ok) toast.success(t('Probe OK'));
              else {
                const appError = toUiAppError(
                  e.detail.error ?? new Error(message),
                  message,
                  'ui',
                  { action: 'identity_sources_wizard.probe_done' }
                );
                notifyError(appError);
              }
            }}
          />
        </div>
      {/if}

      {#if currentStepKey === 'snapshot'}
        <div class="test-step">
          <h2>{t('Snapshot')}</h2>
          <p class="test-sub">{t('Snapshot Activation, Import Scope and Snapshot Test Run.')}</p>

          <div class="test-summary">
            <div class="summary-row"><strong>{t('Snapshot Activation:')}</strong> {snapshotEnabledSummary ? t('Enabled') : t('Disabled')}</div>
            <div class="summary-row"><strong>{t('Import Scope:')}</strong> {payload.capabilities.import_groups ? t('Users + groups') : t('Users only')}</div>
            <div class="summary-row">
              <strong>{t('Snapshot status:')}</strong>
              <StatusBadge
                status={snapshotStatusLabel(lastSnapshotStatus)}
                label={snapshotStatusLabel(lastSnapshotStatus)}
                variant={snapshotStatusVariant(lastSnapshotStatus)}
                compact={true}
              />
            </div>
            <div class="summary-row"><strong>{t('Snapshot date:')}</strong> {formatSnapshotDate(lastSnapshotAt)}</div>
            <div class="summary-row"><strong>{t('Snapshot version:')}</strong> {lastSnapshotVersion ?? '—'}</div>
            <div class="summary-row">
              <strong>{t('Synchronized objects (snapshot):')}</strong>
              {#if creating || loadingSnapshotCount}
                {t('en cours…')}
              {:else if !createDone}
                {t('available after creation')}
              {:else if lastSnapshotObjectsCount !== null}
                {lastSnapshotObjectsCount}
                {#if lastSnapshotUsersCount !== null || lastSnapshotGroupsCount !== null || lastSnapshotMembershipsCount !== null}
                  <span class="test-desc">{t('(users: {value}, groups: {value2}, memberships: {value3})', { value: (lastSnapshotUsersCount ?? 0), value2: (lastSnapshotGroupsCount ?? 0), value3: (lastSnapshotMembershipsCount ?? 0) })}</span>
                {/if}
              {:else}
                —
              {/if}
            </div>
            {#if createdSourceId}
              <div class="summary-row"><strong>{t('Source ID:')}</strong> {createdSourceId}</div>
            {/if}
            {#if snapshotCountNote}
              <div class="summary-row test-desc">{snapshotCountNote}</div>
            {/if}
          </div>

          <div class="snapshot-sync-card">
            <div class="snapshot-sync-head">
              <div>
                <div class="snapshot-sync-title">{t('Snapshot Test Run')}</div>
                <div class="snapshot-sync-sub">
                  {t('Lance le premier snapshot pour hydrater la BDD (date, version, objets).')}
                </div>
              </div>
              <button
                type="button"
                class="b2s-btn-test snapshot-sync-btn"
                class:is-success={snapshotInitState === 'success'}
                disabled={creating || snapshotInitState === 'running' || (createDone && !createdSourceId)}
                on:click={startInitialSnapshotSync}
              >
                {#if creating}{t('Creating…')}{:else if snapshotInitState === 'running'}{t('Synchronizing…')}{:else if snapshotInitState === 'success'}{t('Resync snapshot')}{:else}{t('Initialize snapshot')}{/if}
              </button>
            </div>

            {#if !createDone}
              <div class="snapshot-sync-placeholder">{t('The first click creates the source and starts the initial snapshot.')}</div>
            {:else if !createdSourceId}
              <div class="snapshot-sync-placeholder">{t('Source created, but identifier not found to start synchronization.')}</div>
            {:else}
              <div class="snapshot-progress-wrap" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(snapshotInitProgress)}>
                <div class="snapshot-progress-track">
                  <div class="snapshot-progress-fill" style={`width: ${Math.max(0, Math.min(100, snapshotInitProgress))}%`}></div>
                </div>
                <span class="snapshot-progress-value">{Math.round(snapshotInitProgress)}%</span>
              </div>

              {#if snapshotInitStatusText}
                <div class="snapshot-sync-status">{snapshotInitStatusText}</div>
              {/if}

              <div class="snapshot-steps">
                {#each snapshotInitSteps as syncStep}
                  <div class={`snapshot-step ${syncStep.state}`}>
                    <span class="snapshot-step-dot" aria-hidden="true"></span>
                    <div class="snapshot-step-body">
                      <div class="snapshot-step-label">{syncStep.label}</div>
                      <div class="snapshot-step-desc">{syncStep.description}</div>
                    </div>
                  </div>
                {/each}
              </div>

              {#if snapshotInitError}
                <InlineAlert tone="error">{snapshotInitError}</InlineAlert>
              {/if}
            {/if}
          </div>
        </div>
      {/if}

      {#if currentStepKey === 'review'}
        <div class="test-step">
          <h2>{t('Review')}</h2>
          <p class="test-sub">{t('Review configuration summary before final creation.')}</p>
          {#if testResult}
            <div class={`test-banner ${testResult.ok ? 'ok' : 'err'}`}>
              {testResult.ok ? t('Test OK') : t('Test failed')}
            </div>
          {/if}

          <div class="test-list">
            {#each testResult?.checks ?? [] as c}
              <div class={`test-row ${c.ok ? 'ok' : 'err'}`}>
                <div class="test-left">
                  <span class="test-icon" aria-hidden="true">
                    <i class={`bi ${c.ok ? 'bi-check-circle-fill' : 'bi-x-circle-fill'}`}></i>
                  </span>
                  <div>
                    <div class="test-title">{c.key}</div>
                    {#if c.message}
                      <div class="test-desc">{c.message}</div>
                    {/if}
                  </div>
                </div>
                <div class={`test-status ${c.ok ? 'ok' : 'err'}`}>
                  {c.ok ? 'OK' : t('Error')}
                  {#if !c.ok}
                    <i class="bi bi-chevron-right" aria-hidden="true"></i>
                  {/if}
                </div>
              </div>
            {/each}

            {#if !testResult}
              <div class="test-row empty">{t('No tests have been run yet.')}</div>
            {/if}
          </div>

          {#if testError}
            <InlineAlert tone="error">{testError}</InlineAlert>
          {/if}

          <div class="test-summary">
            <div class="summary-row"><strong>{t('Name:')}</strong> {payload.name || resolveName()}</div>
            <div class="summary-row"><strong>{t('Identity source:')}</strong> {t('Active Directory - {value}', { value: (payload.host || 'corp.local') })}</div>
            <div class="summary-row"><strong>{t('Host / IP:')}</strong> {payload.host || adHostInput || 'dc1.corp.local'}</div>
            <div class="summary-row"><strong>{t('Base DN:')}</strong> {payload.base_dn || 'DC=corp,DC=local'}</div>
            <div class="summary-row"><strong>{t('Bind DN:')}</strong> {payload.bind_dn || 'svc_ad_bind'}</div>
            <div class="summary-row">
              <strong>{t('Snapshot:')}</strong>
              <StatusBadge
                status={snapshotEnabledSummary ? 'enabled' : 'disabled'}
                label={snapshotEnabledSummary ? 'enabled' : 'disabled'}
                variant={snapshotEnabledSummary ? 'success' : 'disabled'}
                compact={true}
              />
            </div>
            <div class="summary-row"><strong>{t('First snapshot automatic after creation:')}</strong> {firstSnapshotAutomaticSummary ? 'yes' : 'no'}</div>
            <div class="summary-row"><strong>{t('Import scope:')}</strong> {payload.capabilities.import_groups ? t('Users + groups') : t('Users only')}</div>
            <div class="summary-row">
              <strong>{t('Probe result:')}</strong>
              <StatusBadge
                status={probeSummaryStatus}
                label={probeSummaryStatus}
                variant={snapshotTestStatusVariant(probeSummaryStatus)}
                compact={true}
              />
            </div>
            <div class="summary-row">
              <strong>{t('Snapshot test status:')}</strong>
              <StatusBadge
                status={snapshotTestSummaryStatus}
                label={snapshotTestSummaryStatus}
                variant={snapshotTestStatusVariant(snapshotTestSummaryStatus)}
                compact={true}
              />
            </div>
            {#if snapshotEnabledSummary}
              <div class="summary-row">
                <strong>{t('Snapshot status:')}</strong>
                <StatusBadge
                  status={snapshotStatusLabel(lastSnapshotStatus)}
                  label={snapshotStatusLabel(lastSnapshotStatus)}
                  variant={snapshotStatusVariant(lastSnapshotStatus)}
                  compact={true}
                />
              </div>
              <div class="summary-row"><strong>{t('Snapshot date:')}</strong> {formatSnapshotDate(lastSnapshotAt)}</div>
              <div class="summary-row"><strong>{t('Snapshot version:')}</strong> {lastSnapshotVersion ?? '—'}</div>
              {#if snapshotCountNote}
                <div class="summary-row test-desc">{snapshotCountNote}</div>
              {/if}
            {/if}
          </div>

          {#if createError}
            <div class="alert error">{createError}</div>
          {/if}
        </div>
      {/if}

      <div class="actions" class:actions--centered={currentStepKey === 'type'}>
        {#if step > 1}
          <button class="b2s-btn b2s-btn-secondary" type="button" on:click={back}>{t('Back')}</button>
        {/if}
        {#if step < maxStep}
          <button class="b2s-btn b2s-btn-primary" type="button" disabled={!canContinue} on:click={next}>{t('Continue')}</button>
        {:else}
          <button class="b2s-btn b2s-btn-primary" type="button" on:click={finish} disabled={creating}>
            {#if creating}
              {t('Creating…')}
            {:else if createDone}
              {t('Close')}
            {:else}
              {t('Finish')}
            {/if}
          </button>
        {/if}
      </div>
    </div>
  </div>
</div>

  <style>
   :global(.is-wizard-backdrop) {
     /* uses shared .b2s-wizard-backdrop */
   }

   :global(.is-wizard-backdrop--clear) {
     background: transparent;
   }

  .is-wizard {
    width: 100%;
  }

  .is-wizard-shell {
    background: transparent;
    border-radius: 0;
    padding: 8px 8px 0;
    box-shadow: none;
    overflow: hidden;
  }

  .is-wizard-header {
    text-align: center;
    margin-bottom: 24px;
  }

  .is-wizard-header h1 {
    margin: 0;
    font-size: var(--b2s-fs-page-title);
    font-weight: 900;
    color: #0f172a;
  }

  .is-wizard-header p {
    margin-top: 8px;
    font-size: var(--b2s-fs-md);
    color: #64748b;
  }

  .is-card {
    background: transparent;
  }

  h2 {
    margin: 0 0 16px;
    font-size: var(--b2s-fs-xl);
    font-weight: 800;
    color: #0f172a;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin-top: 6px;
  }

  .card {
    border: 2px solid #e5e7eb;
    border-radius: var(--b2s-radius-lg);
    padding: 20px 18px 18px;
    background: #ffffff;
    text-align: left;
    cursor: pointer;
    transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease, background 160ms ease;
    position: relative;
    overflow: hidden;
  }

  .card__icon {
    width: 44px;
    height: 44px;
    border-radius: var(--b2s-radius-md);
    background: linear-gradient(135deg, rgba(11, 21, 48, 0.15), rgba(30, 58, 138, 0.2));
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
    color: var(--b2s-topbar-bg, #0b1530);
    font-size: 20px;
  }

  .card::after {
    content: "";
    position: absolute;
    top: -30px;
    right: -30px;
    width: 90px;
    height: 90px;
    border-radius: var(--b2s-radius-pill);
    background: radial-gradient(circle at center, rgba(11, 21, 48, 0.16), transparent 60%);
    pointer-events: none;
  }

  .card:hover {
    border-color: var(--b2s-topbar-bg, #0b1530);
    background: #f8fafc;
    transform: translateY(-2px);
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.1);
  }

  .card.selected {
    border-color: var(--b2s-topbar-bg, #0b1530);
    background: rgba(11, 21, 48, 0.06);
    box-shadow: 0 18px 40px rgba(11, 21, 48, 0.18);
  }

  .card.disabled,
  .card:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
    background: #f8fafc;
  }

  .card__title {
    font-weight: 800;
    font-size: var(--b2s-fs-lg);
    color: #0f172a;
  }

  .card__desc {
    color: #64748b;
    font-size: var(--b2s-fs-sm);
    margin-top: 6px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
  }

  .field label {
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field input {
    width: 100%;
    padding: 12px 14px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid #cbd5e1;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
    color: #0f172a;
  }

  .field select {
    width: 100%;
    padding: 12px 14px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid #cbd5e1;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
    color: #0f172a;
    background: #ffffff;
  }

  .error {
    margin-top: 6px;
    font-size: var(--b2s-fs-xs);
    color: #b91c1c;
    font-weight: 700;
  }

  .hint {
    margin-top: 6px;
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    font-weight: 600;
  }

  .hint.ok {
    color: #15803d;
  }

  .field input:focus-visible {
    outline: none;
    border-color: var(--b2s-topbar-bg, #0b1530);
    box-shadow: 0 0 0 4px rgba(11, 21, 48, 0.18);
  }

  .capabilities {
    padding: 4px 0 6px;
  }

  .capabilities-head {
    margin-bottom: 16px;
  }

  .step-hint {
    margin: 0 0 12px;
    font-size: var(--b2s-fs-sm);
    color: #64748b;
  }

  .protocol-switch {
    display: inline-flex;
    gap: 6px;
    padding: 4px;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    margin-bottom: 12px;
  }

  .protocol-btn {
    border: none;
    background: transparent;
    padding: 6px 10px;
    border-radius: var(--b2s-radius-pill);
    font-weight: 800;
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    cursor: pointer;
  }

  .protocol-btn.active {
    background: var(--b2s-topbar-bg, #0b1530);
    color: #ffffff;
    box-shadow: 0 8px 16px rgba(11, 21, 48, 0.24);
  }

  .protocol-switch {
    border-color: rgba(11, 21, 48, 0.2);
    background: rgba(11, 21, 48, 0.06);
  }

  .capabilities-sub {
    margin: 2px 0 16px;
    font-size: var(--b2s-fs-md);
    color: #64748b;
  }

  .cap-card {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    background: transparent;
    border: 0;
    border-radius: 0;
    box-shadow: none;
    padding: 0;
  }

  .cap-option {
    min-height: 76px;
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 11px;
    align-items: center;
    padding: 12px;
    border: 1px solid #d9e2ef;
    border-radius: var(--b2s-radius-sm);
    background: #ffffff;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    cursor: pointer;
  }

  .cap-option-icon {
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: #eff6ff;
    color: #0b63f4;
    font-size: 1rem;
  }

  .cap-option-copy {
    min-width: 0;
  }

  .cap-option-copy strong,
  .cap-option-copy small {
    display: block;
  }

  .cap-option-copy strong {
    color: #071638;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
  }

  .cap-option-copy small {
    margin-top: 4px;
    color: #596985;
    font-size: var(--b2s-fs-xs);
    line-height: 1.25;
  }

  .cap-switch {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: #cbd5e1;
    position: relative;
    cursor: pointer;
    transition: background 0.16s ease;
  }

  .cap-switch::after {
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

  .cap-switch:checked {
    background: var(--b2s-topbar-bg, #0b1530);
  }

  .cap-switch:checked::after {
    transform: translateX(15px);
  }

  .test-step {
    padding: 4px 0;
  }

  .test-sub {
    margin: 4px 0 16px;
    font-size: var(--b2s-fs-md);
    color: #64748b;
  }

  .test-banner {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    margin-bottom: 10px;
  }

  .test-banner.ok {
    background: #dcfce7;
    color: #166534;
  }

  .test-banner.err {
    background: #fee2e2;
    color: #b91c1c;
  }

  .test-list {
    background: #ffffff;
    border-radius: var(--b2s-radius-lg);
    border: 1px solid #e2e8f0;
    box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
    padding: 8px 10px;
  }

  .test-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 8px;
    border-radius: var(--b2s-radius-md);
  }

  .test-row + .test-row {
    border-top: 1px solid #edf2f7;
  }

  .test-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .test-icon {
    width: 22px;
    height: 22px;
    border-radius: var(--b2s-radius-pill);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #dcfce7;
    color: #16a34a;
    font-size: 13px;
  }

  .test-row.err .test-icon {
    background: #fee2e2;
    color: #dc2626;
  }

  .test-title {
    font-weight: 800;
    color: #0f172a;
  }

  .test-desc {
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    margin-top: 2px;
  }

  .test-status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 800;
    color: #15803d;
  }

  .test-status.err {
    color: #b91c1c;
  }

  .test-summary {
    margin-top: 14px;
    background: #f8fafc;
    border-radius: var(--b2s-radius-md);
    border: 1px solid #e2e8f0;
    padding: 12px 14px;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
    color: #0f172a;
  }

  .summary-row + .summary-row {
    margin-top: 6px;
  }

  .snapshot-sync-card {
    margin-top: 14px;
    border: 1px solid #e2e8f0;
    border-radius: var(--b2s-radius-lg);
    background: #ffffff;
    padding: 12px;
  }

  .snapshot-sync-head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    margin-bottom: 10px;
  }

  .snapshot-sync-title {
    font-size: var(--b2s-fs-sm);
    font-weight: 900;
    color: #0f172a;
  }

  .snapshot-sync-sub {
    margin-top: 2px;
    font-size: var(--b2s-fs-xs);
    color: #64748b;
  }

  .snapshot-sync-btn {
    white-space: nowrap;
  }

  .snapshot-sync-placeholder {
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    padding: 6px 2px;
  }

  .snapshot-progress-wrap {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    align-items: center;
  }

  .snapshot-progress-track {
    height: 10px;
    border-radius: var(--b2s-radius-pill);
    overflow: hidden;
    background: #e2e8f0;
  }

  .snapshot-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #0ea5e9 0%, #2563eb 55%, #16a34a 100%);
    transition: width 220ms ease;
  }

  .snapshot-progress-value {
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    color: #334155;
    min-width: 40px;
    text-align: right;
  }

  .snapshot-sync-status {
    margin-top: 8px;
    font-size: var(--b2s-fs-xs);
    color: #475569;
    font-weight: 700;
  }

  .snapshot-steps {
    margin-top: 10px;
    display: grid;
    gap: 8px;
  }

  .snapshot-step {
    display: grid;
    grid-template-columns: 10px 1fr;
    gap: 10px;
    align-items: flex-start;
    padding: 8px 10px;
    border: 1px solid #e2e8f0;
    border-radius: var(--b2s-radius-md);
    background: #f8fafc;
  }

  .snapshot-step-dot {
    width: 10px;
    height: 10px;
    border-radius: var(--b2s-radius-pill);
    margin-top: 5px;
    background: #94a3b8;
  }

  .snapshot-step.running {
    border-color: rgba(37, 99, 235, 0.35);
    background: #eff6ff;
  }

  .snapshot-step.running .snapshot-step-dot {
    background: #2563eb;
  }

  .snapshot-step.done {
    border-color: rgba(22, 163, 74, 0.35);
    background: #f0fdf4;
  }

  .snapshot-step.done .snapshot-step-dot {
    background: #16a34a;
  }

  .snapshot-step.error {
    border-color: rgba(220, 38, 38, 0.35);
    background: #fef2f2;
  }

  .snapshot-step.error .snapshot-step-dot {
    background: #dc2626;
  }

  .snapshot-step-label {
    font-size: var(--b2s-fs-xs);
    font-weight: 800;
    color: #0f172a;
  }

  .snapshot-step-desc {
    margin-top: 1px;
    font-size: var(--b2s-fs-xs);
    color: #64748b;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px 16px;
  }

  .field--full {
    grid-column: 1 / -1;
  }

  .check {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-top: 12px;
    font-weight: 700;
    color: #0f172a;
  }

  .actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-top: 22px;
    flex-wrap: wrap;
  }

  .actions.actions--centered {
    justify-content: center;
  }

  .test-actions {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 14px;
    width: 100%;
  }

  .actions .b2s-btn {
    flex: 1 1 160px;
  }

  .alert {
    margin-top: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-md);
    font-weight: 700;
    font-size: var(--b2s-fs-sm);
  }

  .alert.error {
    background: #fef2f2;
    color: #991b1b;
  }

  @media (max-width: 900px) {
    .cards,
    .grid {
      grid-template-columns: 1fr;
    }

    .actions {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
