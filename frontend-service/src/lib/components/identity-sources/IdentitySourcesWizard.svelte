<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { toast } from '$lib/utils/toast';
  import RunProbeButton from '$lib/components/common/RunProbeButton.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { buildIdentitySourceProbeRequest } from '$lib/probe/probe-builders';
  import { resolveCredentials } from '$lib/auth/credentials-service';
  import { isValidHostname, isValidIPv4 } from '$lib/utils/host-validate';
  import { resolveStatusVariant } from '$lib/constants/status';
  import { notifyError, toAppError, type AppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
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
  } from '$lib/services/identity-sources.helpers';
  import { jobsStore } from '$lib/stores/app/jobs.store';
  import { snapshotStore } from '$lib/stores/features/snapshot.store';

  export let onTest: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<{
    ok: boolean;
    checks: Array<{ key: string; ok: boolean; message?: string }>;
    status?: string;
    job_id?: string | number;
  }>;
  export let onCreate: (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => Promise<IdentitySourceCreateResult>;
  export let existingNames: string[] = [];

  const dispatch = createEventDispatcher();

  const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

  function normalizeWizardError(
    error: unknown,
    fallback: string,
    source: AppError['source'],
    context?: Record<string, unknown>
  ): AppError {
    const normalized = toAppError(error, { source });
    const appError = GENERIC_ERROR_MESSAGES.has(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
    logAppError(appError, context);
    return appError;
  }

  type WizardStepKey = 'type' | 'capabilities' | 'connection' | 'snapshot' | 'review';
  type WizardStepItem = { key: WizardStepKey; label: string };
  const stepsWithoutSnapshot: WizardStepItem[] = [
    { key: 'type', label: 'Select Type' },
    { key: 'capabilities', label: 'Capabilities' },
    { key: 'connection', label: 'Connection' },
    { key: 'review', label: 'Review' }
  ];
  const stepsWithSnapshot: WizardStepItem[] = [
    { key: 'type', label: 'Select Type' },
    { key: 'capabilities', label: 'Capabilities' },
    { key: 'connection', label: 'Connection' },
    { key: 'snapshot', label: 'Snapshot' },
    { key: 'review', label: 'Review' }
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
      label: 'Dispatch',
      description: 'Request sent to orchestrator',
      state: 'pending'
    },
    {
      key: 'queued',
      label: 'Queue',
      description: 'Job scheduled on backend',
      state: 'pending'
    },
    {
      key: 'collect',
      label: 'Collecte',
      description: 'Collecte LDAP et projection snapshot',
      state: 'pending'
    },
    {
      key: 'persist',
      label: 'Persist',
      description: 'Date/version/accounts persisted in DB',
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
  let ldapsVerifyTls = true;
  let ldapsCaRef = '';
  let ldapsServerName = '';
  let ldapsMinTls: '1.2' | '1.3' = '1.2';
  let ldapsChannelBinding: 'strict' | 'optional' | 'disabled' = 'strict';
  let ldapsSigningRequired = true;
  let ldapsBindType: 'simple' | 'gssapi' = 'gssapi';
  let krbRealm = '';
  let krbKdc = '';
  let krbPrincipal = '';
  let krbKeytabRef = '';

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
      // UI-only LDAPS advanced settings (kept for client-side validation / future backend support)
      _ldaps: payload.protocol === 'ldaps'
        ? {
            verify_tls: ldapsVerifyTls,
            ca_ref: ldapsCaRef || null,
            server_name: ldapsServerName || null,
            min_tls: ldapsMinTls,
            channel_binding: ldapsChannelBinding,
            signing_required: ldapsSigningRequired,
            bind_type: ldapsBindType,
            kerberos: ldapsBindType === 'gssapi'
              ? {
                  realm: krbRealm || null,
                  kdc: krbKdc || null,
                  principal: krbPrincipal || null,
                  keytab_ref: krbKeytabRef || null
                }
              : null
          }
        : null,
      /**
       * 🔐 INTERNAL ONLY
       * Used ONLY by onTest / onCreate to request a backend-managed secret_ref.
       */
      _secret: uiBindPassword || undefined
    };
  }

  function next() {
    if ((currentStepKey === 'type' || currentStepKey === 'connection') && isDuplicateSourceName()) {
      toast.error('This name already exists. Please choose another one.');
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

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
            note: 'Snapshot metadata loaded',
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
      const appError = normalizeWizardError(e, 'Lecture du snapshot impossible.', 'ui', {
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
        snapshotInitStatusText = 'Snapshot initialization failed.';
        return;
      }

      await finish();
      if (!createdSourceId) {
        snapshotInitError = createError ?? 'Unable to create source before snapshot initialization.';
        snapshotInitStatusText = 'Snapshot initialization failed.';
        return;
      }
    }

    jobsStore.startJob(snapshotJobInput(Number(createdSourceId)), {
      message: 'Snapshot sync running'
    });
    snapshotStore.setRunning(Number(createdSourceId), 'Initial snapshot sync running');

    snapshotInitState = 'running';
    snapshotInitProgress = 6;
    snapshotInitError = null;
    snapshotInitStatusText = 'Dispatching snapshot request…';
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
        if (normalized) snapshotInitStatusText = `Snapshot status: ${normalized}`;

        snapshotInitProgress = Math.min(84, 42 + i * 1.1);

        if (['FAILED', 'ERROR', 'CANCELED', 'CANCELLED'].includes(normalized)) {
          throw new Error(`Snapshot ${normalized.toLowerCase()}.`);
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
      snapshotInitStatusText = 'Refreshing persisted metadata…';

      await loadSnapshotCounts(Number(createdSourceId));

      updateSnapshotInitStep('persist', 'done');
      snapshotInitProgress = 100;
      snapshotInitState = 'success';
      snapshotInitStatusText = 'Initial snapshot persisted in database.';
      jobsStore.succeedJob(snapshotJobInput(Number(createdSourceId)), {
        message: 'Initial snapshot persisted',
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
      toast.success('Snapshot synchronized.');
    } catch (e: unknown) {
      failSnapshotInitRunningStep();
      snapshotInitState = 'failed';
      snapshotInitProgress = Math.max(snapshotInitProgress, 34);
      const appError = normalizeWizardError(e, 'Unable to initialize first snapshot.', 'ui', {
        action: 'identity_sources_wizard.start_initial_snapshot_sync',
        sourceId: createdSourceId
      });
      snapshotInitError = appError.message;
      snapshotInitStatusText = 'Snapshot initialization failed.';
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
          note: 'Identity source created from wizard'
        });
        await loadSnapshotCounts(sourceId);
      }
      createDone = true;
    } catch (e: unknown) {
      const appError = normalizeWizardError(e, 'Creation failed', 'ui', {
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
      resolveHint = { ok: false, message: 'Enter a hostname or an IP.' };
      return;
    }
    if (isValidIPv4(value)) {
      resolveHint = { ok: true, message: 'Valid IP.' };
      return;
    }
    if (isValidHostname(value)) {
      resolveHint = { ok: true, message: 'Valid hostname.' };
      return;
    }
    resolveHint = { ok: false, message: 'Invalid hostname/IP format.' };
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
      <h1 id="identity-sources-wizard-title">Connect Identity Source</h1>
      <p>Configure Active Directory (LDAP) or an OIDC provider to import identities.</p>
    </div>

    <div class="is-stepper b2s-wizard-stepper" aria-label="Wizard progress">
      {#each activeSteps as wizardStep, idx}
        <div class="is-step b2s-wizard-step">
          <div class="num" class:active={step >= idx + 1}>{idx + 1}</div>
          <div class="label" class:active={step >= idx + 1}>{wizardStep.label}</div>
        </div>
        {#if idx < activeSteps.length - 1}
          <div class="line" class:active={step >= idx + 2}></div>
        {/if}
      {/each}
    </div>

    <div class="is-card">
      {#if currentStepKey === 'type'}
        <h2>Select Type</h2>

        <div class="field">
          <label for="identity-source-name">Name</label>
          <input
            id="identity-source-name"
            bind:value={payload.name}
            placeholder="AD Corp (prod)"
            autocomplete="off"
          />
        </div>

        <div class="cards">
          <button type="button" class="card" class:selected={payload.type === 'ad'} on:click={() => selectType('ad')}>
            <div class="card__icon"><i class="bi bi-diagram-3"></i></div>
            <div class="card__title">Active Directory / LDAP</div>
            <div class="card__desc">LDAP server for Microsoft Active Directory or generic LDAP</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title="Coming soon"
          >
            <div class="card__icon"><i class="bi bi-key"></i></div>
            <div class="card__title">OIDC / SCIM 2.0</div>
            <div class="card__desc">Provision identities via OIDC / SCIM</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title="Coming soon"
          >
            <div class="card__icon"><i class="bi bi-cloud"></i></div>
            <div class="card__title">Azure AD</div>
            <div class="card__desc">Microsoft Entra ID connector</div>
          </button>
          <button
            type="button"
            class="card disabled"
            disabled
            aria-disabled="true"
            title="Coming soon"
          >
            <div class="card__icon"><i class="bi bi-amazon"></i></div>
            <div class="card__title">Amazon IAM</div>
            <div class="card__desc">AWS identity source</div>
          </button>
        </div>
      {/if}

      {#if currentStepKey === 'capabilities'}
        <div class="capabilities">
          <div class="capabilities-head">
            <h2>Capabilities</h2>
            <p class="capabilities-sub">Enable features available for this source.</p>
          </div>

          <div class="cap-card">
            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-person-check" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>Authenticate users</strong>
                <small>Allow this source to authenticate users.</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.auth} />
            </label>

            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>Import groups</strong>
                <small>Import groups from this source.</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.import_groups} />
            </label>

            <label class="cap-option">
              <span class="cap-option-icon"><i class="bi bi-cloud-arrow-down" aria-hidden="true"></i></span>
              <span class="cap-option-copy">
                <strong>Snapshot inventory</strong>
                <small>Synchronize directory inventory and health metadata.</small>
              </span>
              <input class="cap-switch" type="checkbox" bind:checked={payload.capabilities.snapshot_enabled} />
            </label>
          </div>

          {#if payload.capabilities.snapshot_enabled}
            <div class="hint ok">Snapshot inventory will add one additional configuration step.</div>
          {/if}
        </div>
      {/if}

      {#if currentStepKey === 'connection'}
      <h2>Connection</h2>
      <p class="step-hint">Provide LDAP/LDAPS parameters. Fields marked “Required” must be filled in.</p>
      {#if payload.type === 'ad'}
        <div class="grid">
            <div class="field field--full">
              <label for="identity-source-name-step3">Name</label>
              <input
                id="identity-source-name-step3"
                bind:value={payload.name}
                placeholder="AD Corp (prod)"
                autocomplete="off"
              />
              {#if showStep3Errors && !payload.name?.trim()}
                <span class="error">Required</span>
              {:else if showStep3Errors && isDuplicateSourceName()}
                <span class="error">This name already exists</span>
              {/if}
            </div>

            <div class="field">
              <label for="identity-source-host">Hostname / IP</label>
              <div class="b2s-input-with-action">
                <input
                  id="identity-source-host"
                  bind:value={adHostInput}
                  placeholder="dc1.corp.local or 192.168.10.10"
                />
                <button
                  class="b2s-input-action"
                  type="button"
                  aria-label="Resolve host"
                  on:click={resolveHostInput}
                >
                  <i class="bi bi-search" aria-hidden="true"></i>
                </button>
              </div>
              {#if showStep3Errors && !adHostInput}
                <span class="error">Required</span>
              {:else if showStep3Errors && adHostInput && !isValidIPv4(adHostInput) && !isValidHostname(adHostInput)}
                <span class="error">Invalid hostname / IP</span>
              {/if}
              {#if resolveHint}
                <span class={resolveHint.ok ? 'hint ok' : 'hint'}>{resolveHint.message}</span>
              {/if}
            </div>
            <div class="field">
              <label>Protocol</label>
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
              <label for="identity-source-port">Port</label>
              <input
                id="identity-source-port"
                type="number"
                bind:value={payload.port}
              />
              {#if showStep3Errors && !payload.port}
                <span class="error">Required</span>
              {/if}
            </div>
            <div class="field">
              <label for="identity-source-base-dn">Base DN</label>
              <input
                id="identity-source-base-dn"
                bind:value={payload.base_dn}
                placeholder="DC=corp,DC=local"
              />
              {#if showStep3Errors && !payload.base_dn}
                <span class="error">Required</span>
              {/if}
            </div>
            <div class="field">
              <label for="identity-source-bind-dn">Bind DN</label>
              <input
                id="identity-source-bind-dn"
                bind:value={payload.bind_dn}
                placeholder="svc_ad_bind"
              />
              {#if showStep3Errors && !payload.bind_dn}
                <span class="error">Required</span>
              {/if}
            </div>

            <div class="field">
              <label for="identity-source-bind-password">Bind password</label>
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
                  aria-label={showBindPassword ? 'Hide password' : 'Show password'}
                  on:click={() => (showBindPassword = !showBindPassword)}
                >
                  <i class={`bi ${showBindPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
                </button>
              </div>
              {#if showStep3Errors && !uiBindPassword && !payload.bind_password_ref}
                <span class="error">Required</span>
              {/if}
            </div>

            <div class="field field--full">
              {#if isNtlmAuth}
                <span class="hint">⚠️ In hardened environments (CIS), Kerberos is recommended. Suggested format: user@realm.</span>
              {/if}
              {#if isKerberosAuth}
                <span class="hint ok">Kerberos detected. Prerequisites: DNS SRV Kerberos, synchronized NTP, ports 88/464 open, krb5.conf mounted in the runner.</span>
              {/if}
            </div>
            {#if protocolChoice === 'ldaps'}
              <div class="field">
                <label>Bind type (LDAPS)</label>
                <div class="protocol-switch">
                  <button
                    type="button"
                    class="protocol-btn"
                    class:active={ldapsBindType === 'gssapi'}
                    on:click={() => (ldapsBindType = 'gssapi')}
                  >
                    Kerberos (GSSAPI)
                  </button>
                  <button
                    type="button"
                    class="protocol-btn"
                    class:active={ldapsBindType === 'simple'}
                    on:click={() => (ldapsBindType = 'simple')}
                  >
                    Simple Bind
                  </button>
                </div>
                {#if ldapsBindType === 'gssapi'}
                  <span class="hint ok">Recommended for Protected Users. Requires krb5.conf, keytab, DNS SRV, NTP.</span>
                {:else}
                  <span class="hint">Simple bind must be LDAPS only and may require LDAP signing + channel binding.</span>
                {/if}
              </div>

              {#if ldapsBindType === 'gssapi'}
                <div class="field">
                  <label for="identity-source-krb-realm">Kerberos Realm</label>
                  <input
                    id="identity-source-krb-realm"
                    placeholder="CORP.LOCAL"
                    bind:value={krbRealm}
                  />
                </div>
                <div class="field">
                  <label for="identity-source-krb-kdc">KDC (optional)</label>
                  <input
                    id="identity-source-krb-kdc"
                    placeholder="dc01.corp.local"
                    bind:value={krbKdc}
                  />
                </div>
                <div class="field">
                  <label for="identity-source-krb-principal">Service Principal</label>
                  <input
                    id="identity-source-krb-principal"
                    placeholder="svc_ldap@CORP.LOCAL"
                    bind:value={krbPrincipal}
                  />
                </div>
                <div class="field">
                  <label for="identity-source-krb-keytab">Keytab secret ref</label>
                  <input
                    id="identity-source-krb-keytab"
                    placeholder="secret://krb5/keytab/ldap"
                    bind:value={krbKeytabRef}
                  />
                </div>
              {/if}

              <div class="field">
                <label>TLS validation</label>
                <label class="cap-item">
                  <input class="cap-input" type="checkbox" bind:checked={ldapsVerifyTls} />
                  <span class="cap-check" aria-hidden="true"><i class="bi bi-check-lg"></i></span>
                  <div class="cap-content">
                    <div class="cap-title">Verify TLS chain</div>
                    <div class="cap-desc">Required for production hardening.</div>
                  </div>
                </label>
              </div>
              <div class="field">
                <label for="identity-source-ldaps-ca">CA bundle (secret ref)</label>
                <input
                  id="identity-source-ldaps-ca"
                  placeholder="secret://pki/ca/ldap"
                  bind:value={ldapsCaRef}
                />
              </div>
              <div class="field">
                <label for="identity-source-ldaps-server-name">Expected server name (SAN/CN)</label>
                <input
                  id="identity-source-ldaps-server-name"
                  placeholder="dc01.corp.local"
                  bind:value={ldapsServerName}
                />
              </div>
              <div class="field">
                <label for="identity-source-ldaps-min-tls">Minimum TLS</label>
                <select id="identity-source-ldaps-min-tls" bind:value={ldapsMinTls}>
                  <option value="1.3">TLS 1.3</option>
                  <option value="1.2">TLS 1.2</option>
                </select>
              </div>
              <div class="field">
                <label for="identity-source-ldaps-channel-binding">Channel Binding</label>
                <select id="identity-source-ldaps-channel-binding" bind:value={ldapsChannelBinding}>
                  <option value="strict">Strict</option>
                  <option value="optional">Optional</option>
                  <option value="disabled">Disabled</option>
                </select>
              </div>
              <div class="field">
                <label>LDAP signing required</label>
                <label class="cap-item">
                  <input class="cap-input" type="checkbox" bind:checked={ldapsSigningRequired} />
                  <span class="cap-check" aria-hidden="true"><i class="bi bi-check-lg"></i></span>
                  <div class="cap-content">
                    <div class="cap-title">Require signing (policy)</div>
                    <div class="cap-desc">Aligns with hardened AD policies.</div>
                  </div>
                </label>
              </div>
            {/if}
          </div>
        {:else}
            <div class="grid">
              <div class="field">
              <label for="identity-source-issuer-url">Issuer URL</label>
                <input
                  id="identity-source-issuer-url"
                  bind:value={payload.issuer_url}
                  placeholder="https://issuer.example.com"
                />
              </div>
              <div class="field">
                <label for="identity-source-client-id">Client ID</label>
                <input id="identity-source-client-id" bind:value={payload.client_id} />
              </div>
              <div class="field">
              <label for="identity-source-client-secret">Client Secret</label>
                <input
                  id="identity-source-client-secret"
                  type="password"
                  bind:value={payload.client_secret}
                />
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
            label="Run Probe"
            busyLabel="Running probe…"
            fullWidth={true}
            showIcon={true}
            iconClass="bi bi-activity"
            busyIconClass="bi bi-hourglass-split"
            buttonClass={`se-run-probe-btn sed-btn sed-btn--secondary ${probeStatus === 'success' ? 'is-success' : ''}`}
            hideSuccessPanel={true}
            disabled={!canContinueStep3}
            beforeRun={async () => {
              probeStatus = 'running';
              showStep3Errors = false;
              testError = null;
              jobsStore.startJob(probeWizardJobInput(), {
                message: 'Probe running'
              });
              if (!canContinueStep3) {
                showStep3Errors = true;
                throw new Error('Complete the required connection fields first.');
              }
              const secretRef = await ensureBindSecretRef();
              if (!secretRef && payload.bind_dn?.trim()) {
                throw new Error('Password is required to test the connection (no secret_ref available).');
              }
            }}
            on:done={(e) => {
              const ok = Boolean(e.detail.ok);
              const message = ok
                ? 'Probe OK'
                : (e.detail.error?.message ?? 'Probe failed');

              probeStatus = ok ? 'success' : 'failed';

              testResult = {
                ok,
                checks: [{ key: 'probe', ok, message }]
              };
              testError = ok ? null : message;

              if (ok) {
                jobsStore.succeedJob(probeWizardJobInput(), {
                  message: 'Probe OK',
                  summary: { message }
                });
              } else {
                jobsStore.failJob(probeWizardJobInput(), {
                  message,
                  error: message
                });
              }

              if (ok) toast.success('Probe OK');
              else {
                const appError = normalizeWizardError(
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
          <h2>Snapshot</h2>
          <p class="test-sub">Snapshot Activation, Import Scope and Snapshot Test Run.</p>

          <div class="test-summary">
            <div class="summary-row"><strong>Snapshot Activation:</strong> {snapshotEnabledSummary ? 'Enabled' : 'Disabled'}</div>
            <div class="summary-row"><strong>Import Scope:</strong> {payload.capabilities.import_groups ? 'Users + groups' : 'Users only'}</div>
            <div class="summary-row">
              <strong>Snapshot status:</strong>
              <StatusBadge
                status={snapshotStatusLabel(lastSnapshotStatus)}
                label={snapshotStatusLabel(lastSnapshotStatus)}
                variant={snapshotStatusVariant(lastSnapshotStatus)}
                compact={true}
              />
            </div>
            <div class="summary-row"><strong>Snapshot date:</strong> {formatSnapshotDate(lastSnapshotAt)}</div>
            <div class="summary-row"><strong>Snapshot version:</strong> {lastSnapshotVersion ?? '—'}</div>
            <div class="summary-row">
              <strong>Synchronized objects (snapshot):</strong>
              {#if creating || loadingSnapshotCount}
                en cours…
              {:else if !createDone}
                available after creation
              {:else if lastSnapshotObjectsCount !== null}
                {lastSnapshotObjectsCount}
                {#if lastSnapshotUsersCount !== null || lastSnapshotGroupsCount !== null || lastSnapshotMembershipsCount !== null}
                  <span class="test-desc">(users: {lastSnapshotUsersCount ?? 0}, groups: {lastSnapshotGroupsCount ?? 0}, memberships: {lastSnapshotMembershipsCount ?? 0})</span>
                {/if}
              {:else}
                —
              {/if}
            </div>
            {#if createdSourceId}
              <div class="summary-row"><strong>Source ID:</strong> {createdSourceId}</div>
            {/if}
            {#if snapshotCountNote}
              <div class="summary-row test-desc">{snapshotCountNote}</div>
            {/if}
          </div>

          <div class="snapshot-sync-card">
            <div class="snapshot-sync-head">
              <div>
                <div class="snapshot-sync-title">Snapshot Test Run</div>
                <div class="snapshot-sync-sub">
                  Lance le premier snapshot pour hydrater la BDD (date, version, objets).
                </div>
              </div>
              <button
                type="button"
                class="b2s-btn-test snapshot-sync-btn"
                class:is-success={snapshotInitState === 'success'}
                disabled={creating || snapshotInitState === 'running' || (createDone && !createdSourceId)}
                on:click={startInitialSnapshotSync}
              >
                {#if creating}Creating…{:else if snapshotInitState === 'running'}Synchronizing…{:else if snapshotInitState === 'success'}Resync snapshot{:else}Initialize snapshot{/if}
              </button>
            </div>

            {#if !createDone}
              <div class="snapshot-sync-placeholder">The first click creates the source and starts the initial snapshot.</div>
            {:else if !createdSourceId}
              <div class="snapshot-sync-placeholder">Source created, but identifier not found to start synchronization.</div>
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
                <div class="test-alert">{snapshotInitError}</div>
              {/if}
            {/if}
          </div>
        </div>
      {/if}

      {#if currentStepKey === 'review'}
        <div class="test-step">
          <h2>Review</h2>
          <p class="test-sub">Review configuration summary before final creation.</p>
          {#if testResult}
            <div class={`test-banner ${testResult.ok ? 'ok' : 'err'}`}>
              {testResult.ok ? 'Test OK' : 'Test failed'}
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
                  {c.ok ? 'OK' : 'Error'}
                  {#if !c.ok}
                    <i class="bi bi-chevron-right" aria-hidden="true"></i>
                  {/if}
                </div>
              </div>
            {/each}

            {#if !testResult}
              <div class="test-row empty">No tests have been run yet.</div>
            {/if}
          </div>

          {#if testError}
            <div class="test-alert">{testError}</div>
          {/if}

          <div class="test-summary">
            <div class="summary-row"><strong>Name:</strong> {payload.name || resolveName()}</div>
            <div class="summary-row"><strong>Identity source:</strong> Active Directory - {payload.host || 'corp.local'}</div>
            <div class="summary-row"><strong>Host / IP:</strong> {payload.host || adHostInput || 'dc1.corp.local'}</div>
            <div class="summary-row"><strong>Base DN:</strong> {payload.base_dn || 'DC=corp,DC=local'}</div>
            <div class="summary-row"><strong>Bind DN:</strong> {payload.bind_dn || 'svc_ad_bind'}</div>
            <div class="summary-row">
              <strong>Snapshot:</strong>
              <StatusBadge
                status={snapshotEnabledSummary ? 'enabled' : 'disabled'}
                label={snapshotEnabledSummary ? 'enabled' : 'disabled'}
                variant={snapshotEnabledSummary ? 'success' : 'disabled'}
                compact={true}
              />
            </div>
            <div class="summary-row"><strong>First snapshot automatic after creation:</strong> {firstSnapshotAutomaticSummary ? 'yes' : 'no'}</div>
            <div class="summary-row"><strong>Import scope:</strong> {payload.capabilities.import_groups ? 'Users + groups' : 'Users only'}</div>
            <div class="summary-row">
              <strong>Probe result:</strong>
              <StatusBadge
                status={probeSummaryStatus}
                label={probeSummaryStatus}
                variant={snapshotTestStatusVariant(probeSummaryStatus)}
                compact={true}
              />
            </div>
            <div class="summary-row">
              <strong>Snapshot test status:</strong>
              <StatusBadge
                status={snapshotTestSummaryStatus}
                label={snapshotTestSummaryStatus}
                variant={snapshotTestStatusVariant(snapshotTestSummaryStatus)}
                compact={true}
              />
            </div>
            {#if snapshotEnabledSummary}
              <div class="summary-row">
                <strong>Snapshot status:</strong>
                <StatusBadge
                  status={snapshotStatusLabel(lastSnapshotStatus)}
                  label={snapshotStatusLabel(lastSnapshotStatus)}
                  variant={snapshotStatusVariant(lastSnapshotStatus)}
                  compact={true}
                />
              </div>
              <div class="summary-row"><strong>Snapshot date:</strong> {formatSnapshotDate(lastSnapshotAt)}</div>
              <div class="summary-row"><strong>Snapshot version:</strong> {lastSnapshotVersion ?? '—'}</div>
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
          <button class="b2s-btn-secondary" type="button" on:click={back}>Back</button>
        {/if}
        {#if step < maxStep}
          <button class="b2s-btn-primary" type="button" disabled={!canContinue} on:click={next}>Continue</button>
        {:else}
          <button class="b2s-btn-primary" type="button" on:click={finish} disabled={creating}>
            {#if creating}
              Creating…
            {:else if createDone}
              Close
            {:else}
              Finish
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
    font-size: 26px;
    font-weight: 900;
    color: #0f172a;
  }

  .is-wizard-header p {
    margin-top: 8px;
    font-size: 14px;
    color: #64748b;
  }

  .is-card {
    background: transparent;
  }

  .is-stepper {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    margin: 16px 0 22px;
  }

  .is-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 88px;
  }

  .num {
    width: 30px;
    height: 30px;
    border-radius: 999px;
    border: 2px solid #cbd5e1;
    color: #64748b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    background: transparent;
    transition: background 180ms ease, color 180ms ease, transform 180ms ease;
  }

  .num.active {
    background: var(--b2s-topbar-bg, #0b1530);
    border-color: var(--b2s-topbar-bg, #0b1530);
    color: #ffffff;
    transform: translateY(-1px);
  }

  .label {
    margin-top: 6px;
    font-weight: 700;
    font-size: 12px;
    color: #94a3b8;
  }

  .label.active {
    color: var(--b2s-topbar-bg, #0b1530);
  }

  .line {
    width: 120px;
    height: 2px;
    background: #cbd5e1;
    border-radius: 999px;
    position: relative;
    overflow: hidden;
  }

  .line::after {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--b2s-topbar-bg, #0b1530);
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 220ms ease;
  }

  .line.active::after {
    transform: scaleX(1);
  }

  h2 {
    margin: 0 0 16px;
    font-size: 18px;
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
    border-radius: 18px;
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
    border-radius: 12px;
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
    border-radius: 999px;
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
    font-size: 15px;
    color: #0f172a;
  }

  .card__desc {
    color: #64748b;
    font-size: 13px;
    margin-top: 6px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
  }

  .field label {
    font-size: 12px;
    font-weight: 800;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field input {
    width: 100%;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid #cbd5e1;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
  }

  .field select {
    width: 100%;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid #cbd5e1;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
    background: #ffffff;
  }

  .error {
    margin-top: 6px;
    font-size: 12px;
    color: #b91c1c;
    font-weight: 700;
  }

  .hint {
    margin-top: 6px;
    font-size: 12px;
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
    font-size: 13px;
    color: #64748b;
  }

  .protocol-switch {
    display: inline-flex;
    gap: 6px;
    padding: 4px;
    border-radius: 999px;
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    margin-bottom: 12px;
  }


  .protocol-btn {
    border: none;
    background: transparent;
    padding: 6px 10px;
    border-radius: 999px;
    font-weight: 800;
    font-size: 12px;
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
    font-size: 14px;
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
    border-radius: 8px;
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
    border-radius: 7px;
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
    font-size: 0.78rem;
    font-weight: 700;
  }

  .cap-option-copy small {
    margin-top: 4px;
    color: #596985;
    font-size: 0.7rem;
    line-height: 1.25;
  }

  .cap-switch {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: 999px;
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
    font-size: 14px;
    color: #64748b;
  }

  .test-banner {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12px;
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
    border-radius: 14px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
    padding: 8px 10px;
  }

  .test-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 8px;
    border-radius: 12px;
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
    border-radius: 999px;
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
    font-size: 12px;
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

  .test-alert {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 12px;
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fde68a;
    font-weight: 700;
  }

  .test-summary {
    margin-top: 14px;
    background: #f8fafc;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    padding: 12px 14px;
    font-size: 13px;
    font-weight: 600;
    color: #0f172a;
  }

  .summary-row + .summary-row {
    margin-top: 6px;
  }

  .snapshot-sync-card {
    margin-top: 14px;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
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
    font-size: 13px;
    font-weight: 900;
    color: #0f172a;
  }

  .snapshot-sync-sub {
    margin-top: 2px;
    font-size: 12px;
    color: #64748b;
  }

  .snapshot-sync-btn {
    white-space: nowrap;
  }

  .snapshot-sync-placeholder {
    font-size: 12px;
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
    border-radius: 999px;
    overflow: hidden;
    background: #e2e8f0;
  }

  .snapshot-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #0ea5e9 0%, #2563eb 55%, #16a34a 100%);
    transition: width 220ms ease;
  }

  .snapshot-progress-value {
    font-size: 12px;
    font-weight: 800;
    color: #334155;
    min-width: 40px;
    text-align: right;
  }

  .snapshot-sync-status {
    margin-top: 8px;
    font-size: 12px;
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
    border-radius: 10px;
    background: #f8fafc;
  }

  .snapshot-step-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
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
    font-size: 12px;
    font-weight: 800;
    color: #0f172a;
  }

  .snapshot-step-desc {
    margin-top: 1px;
    font-size: 11px;
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

  .b2s-btn-test {
    /* uses shared .b2s-btn-test styles */
  }

  .actions .b2s-btn-primary,
  .actions .b2s-btn-secondary {
    border-radius: 12px;
    padding: 12px 18px;
    font-weight: 800;
    font-size: 14px;
    flex: 1 1 160px;
  }

  .actions .b2s-btn-primary {
    background: var(--b2s-topbar-bg, #0b1530);
    border-color: var(--b2s-topbar-bg, #0b1530);
    color: #ffffff;
    box-shadow: 0 12px 24px rgba(11, 21, 48, 0.28);
  }

  .actions .b2s-btn-primary:hover {
    background: #101b39;
    border-color: #101b39;
    box-shadow: 0 16px 28px rgba(11, 21, 48, 0.32);
    transform: translateY(-1px);
  }

  .actions .b2s-btn-secondary {
    background: rgba(11, 21, 48, 0.06);
    border-color: rgba(11, 21, 48, 0.22);
    color: #0b1530;
  }

  .actions .b2s-btn-secondary:hover {
    background: rgba(11, 21, 48, 0.12);
  }

  .alert {
    margin-top: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    font-weight: 700;
    font-size: 13px;
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

    .line {
      width: 60px;
    }
  }
</style>
