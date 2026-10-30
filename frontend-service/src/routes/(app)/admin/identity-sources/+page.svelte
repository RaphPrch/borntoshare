<script lang="ts">
  import EntityActionGroup from '$lib/components/entity/EntityActionGroup.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t, intlLocale } from '$lib/i18n';
  import { browser } from '$app/environment';
  import { onDestroy } from 'svelte';
  import { sleep } from '$lib/utils/values';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import IdentitySourcesWizardModal from '$lib/components/identity-sources/IdentitySourcesWizardModal.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import IdentitySourceDrawer from '$lib/components/identity-sources/IdentitySourceDrawer.svelte';
  import IdentitySourceEditDrawer from '$lib/components/identity-sources/IdentitySourceEditDrawer.svelte';
  import {
    browseIdentitySource,
    createIdentitySource,
    deleteIdentitySource,
    getIdentitySourceInternal,
    listIdentitySources,
    runIdentitySnapshot,
    updateIdentitySource,
    type IdentitySourcePayload
  } from '$lib/api/identity-sources';
  import { getIdentityJob } from '$lib/api/identity';
  import { getHealthSummary, type HealthSummaryDay } from '$lib/api/health';
  import {
    composeIdentitySourceCards,
    type IdentitySourceCardVM,
    type IdentitySourceSortKey
  } from '$lib/mappers/identity-sources.mapper';
  import { buildIdentitySourceProbeRequest } from '$lib/jobs/probe-runner';
  import { runProbeWithUi } from '$lib/jobs/probe-ui';
  import { resolveCredentials } from '$lib/api/credentials';
  import { toast } from '$lib/stores/toast';
  import { dependencyDeleteMessage, isDependencyDeleteError } from '$lib/utils/delete-guard';
  import { notifyError, toAppError, isGenericErrorMessage, toUiAppError } from '$lib/errors';
  import {
    sourceIconClass,
    toneClass,
    extractSnapshotMeta,
    toSnapshotStorePatch,
    toFiniteCount,
    type IdentitySourceInternalMeta
  } from '$lib/utils/identity-sources';
  import { pollJobUntilTerminal } from '$lib/jobs/polling';
  import type { JobUiStatus } from '$lib/jobs/types';
  import { jobsStore, type JobStatus } from '$lib/stores/jobs.store';
  import { selectionStore } from '$lib/stores/selection.store';
  import { snapshotStore } from '$lib/stores/snapshot.store';
  import type { IdentitySourceRow } from '$lib/types/identity-sources';
  import { testIdentitySourceConnection, type IdentitySourceTestPayload } from '$lib/jobs/identity-source-test';

  type SnapshotDebugRow = {
    key: string;
    type: string;
    snapshotVersion: number | null;
    firstName: string | null;
    lastName: string | null;
    displayName: string | null;
    username: string | null;
    email: string | null;
    upn: string | null;
    dn: string | null;
    enabled: string | null;
  };

  export let data: {
    identity_sources?: IdentitySourceRow[];
    fetch_error?: string | null;
  };

  let showWizard = false;
  let showDetailsDrawer = false;
  let selectedSourceId: number | null = null;
  let showEditModal = false;
  let editSource: IdentitySourceRow | null = null;
  let showDeleteModal = false;
  let showDisableUsedConfirm = false;
  let pendingToggleSource: IdentitySourceRow | null = null;
  let busy = false;
  let actionError: string | null = null;
  let selectedSource: IdentitySourceRow | null = null;
  let fetchError: string | null = data?.fetch_error ?? null;
  let listLoading = false;
  let internalLoading = false;
  let internalError: string | null = null;
  let selectedInternal: IdentitySourceInternalMeta | null = null;
  let snapshotDebugLoading = false;
  let snapshotDebugError: string | null = null;
  let snapshotDebugRows: SnapshotDebugRow[] = [];
  let snapshotDebugSourceId: number | null = null;
  let snapshotDebugVersion: number | null = null;
  let hasSources = false;
  let existingSourceNames: string[] = [];
  let sortedCards: IdentitySourceCardVM[] = [];
  let summary = { total: 0, healthy: 0, issues: 0, neverSynced: 0 };
  let selectedCard: IdentitySourceCardVM | null = null;
  let detailCard: IdentitySourceCardVM | null = null;

  let listQuery = '';
  let typeFilter = 'all';
  let statusFilter = 'all';
  let snapshotFilter = 'all';
  let sortBy: IdentitySourceSortKey = 'name-asc';
  let rowsPerPage = 25;
  let currentPage = 1;
  let paginatedCards: IdentitySourceCardVM[] = [];
  let pageStart = 0;
  let pageEnd = 0;
  let totalPages = 1;
  let selectedRecentHealth: Array<{ key: string; label: string; tone: string; title: string; icon: string }> = [];
  let healthSummaryBySourceId: Record<number, HealthSummaryDay[]> = {};
  let healthSummaryLoadingSourceId: number | null = null;
  let healthSummaryLoadedSourceId: number | null = null;

  let sources: IdentitySourceRow[] = data.identity_sources ?? [];

  const typeOptions = [
    { value: 'all', label: t('Type') },
    { value: 'ad', label: t('Active Directory / LDAP') },
    { value: 'oidc', label: 'OIDC' },
    { value: 'local', label: t('Local') }
  ];

  const snapshotOptions = [
    { value: 'all', label: t('Snapshots') },
    { value: 'synced', label: t('Synced') },
    { value: 'never', label: t('Never synced') },
    { value: 'failed', label: t('Failed') },
    { value: 'running', label: t('Running') }
  ];

  const isAdIdentitySource = (source: IdentitySourceRow | null | undefined): boolean => {
    const type = String(source?.type ?? '').trim().toLowerCase();
    return type === 'ad' || type === 'ldap';
  };

  const compactProbeLabel = (card: IdentitySourceCardVM | null): string => {
    if (!card) return '—';
    if (!card.supportsProbe) return t('Not applicable');
    return card.lastProbeLabel || t('Never');
  };

  const compactSnapshotLabel = (card: IdentitySourceCardVM | null): string => {
    if (!card) return '—';
    if (!card.supportsSnapshot) return t('Not applicable');
    return card.lastSnapshotLabel || t('No snapshot yet');
  };

  const patchSourceRuntimeMeta = (sourceId: number, patch: Partial<IdentitySourceRow>) => {
    sources = sources.map((source) => (
      Number(source?.id ?? 0) === Number(sourceId) ? { ...source, ...patch } : source
    ));
  };

  const selectedSourceCard = (source: IdentitySourceRow | null | undefined): IdentitySourceCardVM | null => {
    const id = Number(source?.id ?? 0);
    if (!Number.isFinite(id) || id <= 0) return null;
    return sortedCards.find((card) => Number(card.id) === id) ?? detailCard;
  };

  const baseDnLabel = (card: IdentitySourceCardVM | null): string => {
    const value = String(card?.raw?.base_dn ?? '').trim();
    return value || '—';
  };

  const healthStatusTone = (status: string | null | undefined): string => {
    const normalized = String(status ?? '').trim().toLowerCase();
    if (normalized === 'success') return 'is-success';
    if (normalized === 'running') return 'is-info';
    if (normalized === 'warning') return 'is-warning';
    if (normalized === 'failed') return 'is-error';
    return 'is-muted';
  };

  const healthStatusIcon = (status: string | null | undefined): string => {
    const normalized = String(status ?? '').trim().toLowerCase();
    if (normalized === 'success') return 'bi-check';
    if (normalized === 'running') return 'bi-arrow-repeat';
    if (normalized === 'warning') return 'bi-exclamation';
    if (normalized === 'failed') return 'bi-x';
    return 'bi-dash';
  };

  const healthDateLabel = (value: string, index: number, total: number): string => {
    if (index === total - 1) return t('Today');
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleDateString(intlLocale(), {
      month: 'short',
      day: 'numeric'
    });
  };

  const buildRecentHealth = (card: IdentitySourceCardVM | null, summaryRows: HealthSummaryDay[] | null) => {
    if (!card) return [];
    const rows = Array.isArray(summaryRows) ? summaryRows : [];
    if (rows.length > 0) {
      return rows.map((row, index) => ({
        key: `${card.id}-${row.date || index}`,
        label: healthDateLabel(String(row.date ?? ''), index, rows.length),
        tone: healthStatusTone(row.status),
        title:
          String(row.message ?? '').trim() ||
          t('{String} · {Number} check{value}', { String: String(row.status ?? 'unknown'), Number: Number(row.checks ?? 0), value: (Number(row.checks ?? 0) === 1 ? '' : 's') }),
        icon: healthStatusIcon(row.status)
      }));
    }

    const now = new Date();
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(now);
      date.setDate(now.getDate() - (6 - index));
      return {
        key: `${card.id}-${index}`,
        label:
          index === 6
            ? t('Today')
            : date.toLocaleDateString(intlLocale(), {
                month: 'short',
                day: 'numeric'
              }),
        tone: 'is-muted',
        title: healthSummaryLoadingSourceId === card.id ? t('Loading health history') : t('No health check history'),
        icon: 'bi-dash'
      };
    });
  };

  const loadHealthSummaryForSource = async (sourceId: number, force = false) => {
    const id = Number(sourceId ?? 0);
    if (!Number.isFinite(id) || id <= 0) return;
    if (!force && (healthSummaryLoadingSourceId === id || Array.isArray(healthSummaryBySourceId[id]))) return;
    healthSummaryLoadingSourceId = id;
    try {
      const rows = await getHealthSummary(fetch, 'identity_source', id, 7);
      healthSummaryBySourceId = {
        ...healthSummaryBySourceId,
        [id]: rows
      };
      healthSummaryLoadedSourceId = id;
    } catch (e: unknown) {
      healthSummaryBySourceId = {
        ...healthSummaryBySourceId,
        [id]: []
      };
      healthSummaryLoadedSourceId = id;
      console.warn('identity_source.health_summary_failed', e);
    } finally {
      if (healthSummaryLoadingSourceId === id) {
        healthSummaryLoadingSourceId = null;
      }
    }
  };

  const selectStatusFilter = (value: string) => {
    statusFilter = value;
    currentPage = 1;
  };

  const resetListPage = () => {
    currentPage = 1;
  };

  const goToPage = (page: number) => {
    currentPage = Math.min(Math.max(1, page), totalPages);
  };

  const selectSourceById = (sourceId: number) => {
    const id = Number(sourceId ?? 0);
    if (!Number.isFinite(id) || id <= 0) return;
    selectedSourceId = id;
    showDetailsDrawer = true;
    selectedInternal = null;
    internalError = null;
    snapshotDebugRows = [];
    snapshotDebugError = null;
    snapshotDebugSourceId = null;
    selectionStore.setSelectedIdentitySourceId(id);
    void loadInternal(id);
  };

  $: if (Array.isArray(data?.identity_sources)) {
    sources = data.identity_sources;
  }

  $: if (typeof data?.fetch_error === 'string') {
    fetchError = data.fetch_error;
  }

  const normalizeDebugValue = (value: unknown): string | null => {
    const normalized = String(value ?? '').trim();
    return normalized.length > 0 ? normalized : null;
  };

  const normalizeDebugEnabled = (value: unknown): string | null => {
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    const normalized = String(value ?? '').trim().toLowerCase();
    if (!normalized) return null;
    if (['1', 'true', 'yes', 'y', 'enabled', 'active'].includes(normalized)) return 'true';
    if (['0', 'false', 'no', 'n', 'disabled', 'inactive'].includes(normalized)) return 'false';
    return normalized;
  };

  const loadSnapshotDebugRows = async (sourceId: number, force = false) => {
    const normalizedSourceId = Number(sourceId ?? 0);
    if (!Number.isFinite(normalizedSourceId) || normalizedSourceId <= 0) return;

    if (!force && snapshotDebugSourceId === normalizedSourceId && (snapshotDebugRows.length > 0 || snapshotDebugError)) {
      return;
    }

    snapshotDebugLoading = true;
    snapshotDebugError = null;
    snapshotDebugRows = [];

    try {
      const payload = await browseIdentitySource(fetch, normalizedSourceId, {
        q: '',
        limit: 120,
        principal_type: 'all'
      });

      if (selectedSourceId !== null && Number(selectedSourceId) !== normalizedSourceId) {
        return;
      }

      const rawItems = Array.isArray(payload?.items) ? payload.items : [];
      const version = toFiniteCount(
        selectedInternal?.last_snapshot_version ??
        selectedCard?.raw?.last_snapshot_version
      );

      snapshotDebugRows = rawItems.slice(0, 120).map((row: Record<string, unknown>, index: number) => {
        const type = normalizeDebugValue(row?.type)?.toLowerCase() ?? 'unknown';
        const firstName = normalizeDebugValue(row?.first_name ?? row?.given_name ?? row?.firstname);
        const lastName = normalizeDebugValue(row?.last_name ?? row?.sn ?? row?.surname ?? row?.lastname);
        const displayName = normalizeDebugValue(row?.display_name ?? row?.cn ?? row?.name);
        const username = normalizeDebugValue(row?.username ?? row?.samaccountname ?? row?.sam);
        const email = normalizeDebugValue(row?.email ?? row?.mail);
        const upn = normalizeDebugValue(row?.upn ?? row?.user_principal_name);
        const dn = normalizeDebugValue(row?.dn);
        const key =
          normalizeDebugValue(row?.external_id) ??
          normalizeDebugValue(row?.id) ??
          dn ??
          `${type}-${index}`;

        return {
          key,
          type,
          snapshotVersion: version,
          firstName,
          lastName,
          displayName,
          username,
          email,
          upn,
          dn,
          enabled: normalizeDebugEnabled(row?.enabled ?? row?.is_active ?? row?.active)
        } as SnapshotDebugRow;
      });

      snapshotDebugSourceId = normalizedSourceId;
      snapshotDebugVersion = version;
    } catch (e: unknown) {
      if (selectedSourceId !== null && Number(selectedSourceId) !== normalizedSourceId) {
        return;
      }
      const appError = toUiAppError(e, t('Unable to load snapshot debug rows.'), 'ui', {
        action: 'identity_sources.load_snapshot_debug_rows',
        sourceId: normalizedSourceId
      });
      snapshotDebugRows = [];
      snapshotDebugError = appError.message;
      snapshotDebugSourceId = normalizedSourceId;
      snapshotDebugVersion = null;
    } finally {
      if (selectedSourceId !== null && Number(selectedSourceId) !== normalizedSourceId) {
        return;
      }
      snapshotDebugLoading = false;
    }
  };

  const dependencyMessageFromError = (error: unknown, fallback: string): string => {
    const appError = toAppError(error, { source: 'ui' });
    const message = String(appError.message ?? '').trim();
    return isGenericErrorMessage(message) ? fallback : message;
  };

  const identityProbeJobInput = (sourceId: number) => ({
    entityType: 'identity-source',
    entityId: sourceId,
    action: 'probe'
  } as const);

  const identityProbeJob = (sourceId: number) =>
    $jobsStore[jobsStore.keyOf(identityProbeJobInput(sourceId))] ?? null;

  const identityProbeRunning = (sourceId: number) =>
    identityProbeJob(sourceId)?.status === 'running';

  const identitySnapshotJobInput = (sourceId: number) => ({
    entityType: 'identity-source',
    entityId: sourceId,
    action: 'snapshot'
  } as const);

  const identitySnapshotJob = (sourceId: number) =>
    $jobsStore[jobsStore.keyOf(identitySnapshotJobInput(sourceId))] ?? null;

  // Snapshots running on the server, whoever started them (page reload, another admin, scheduler)
  $: serverSnapshotRunning = new Set(sources.filter((s) => s.snapshot_running).map((s) => Number(s.id)));

  const identitySnapshotRunning = (sourceId: number) =>
    identitySnapshotJob(sourceId)?.status === 'running' || serverSnapshotRunning.has(Number(sourceId));

  // Follow a snapshot started elsewhere until it ends
  let snapshotWatchTimer: ReturnType<typeof setTimeout> | null = null;
  $: if (browser && serverSnapshotRunning.size > 0 && !snapshotWatchTimer) {
    snapshotWatchTimer = setTimeout(async () => {
      await refreshList();
      snapshotWatchTimer = null;
    }, 5000);
  }
  onDestroy(() => {
    if (snapshotWatchTimer) clearTimeout(snapshotWatchTimer);
  });

  const syncSnapshotMetaFromInternal = (sourceId: number, internal: IdentitySourceInternalMeta | null) => {
    snapshotStore.upsert(sourceId, toSnapshotStorePatch(extractSnapshotMeta(internal)));
    patchSourceRuntimeMeta(sourceId, {
      last_probe_at: String((internal as any)?.last_probe_at ?? '').trim() || null,
      probed_at: String((internal as any)?.probed_at ?? '').trim() || null,
      last_snapshot_at: String((internal as any)?.last_snapshot_at ?? '').trim() || null,
      snapshot_at: String((internal as any)?.snapshot_at ?? '').trim() || null,
      last_sync_at: String((internal as any)?.last_sync_at ?? '').trim() || null,
      last_snapshot_status: String((internal as any)?.last_snapshot_status ?? '').trim() || null,
      last_snapshot_version: toFiniteCount((internal as any)?.last_snapshot_version),
      last_snapshot_objects_count: toFiniteCount((internal as any)?.last_snapshot_objects_count),
      last_snapshot_users_count: toFiniteCount((internal as any)?.last_snapshot_users_count),
      last_snapshot_groups_count: toFiniteCount((internal as any)?.last_snapshot_groups_count),
      last_snapshot_memberships_count: toFiniteCount((internal as any)?.last_snapshot_memberships_count),
      updated_at: String((internal as any)?.updated_at ?? '').trim() || null
    });
  };

  const refreshList = async () => {
    listLoading = true;
    fetchError = null;
    try {
      sources = await listIdentitySources(fetch);

      if (selectedSourceId !== null && !sources.some((s) => Number(s?.id ?? 0) === Number(selectedSourceId))) {
        closeDetails();
      }

      if (selectedSource && Number(selectedSource.id) > 0) {
        const refreshedSelected = sources.find((s) => Number(s.id) === Number(selectedSource?.id ?? 0)) ?? null;
        selectedSource = refreshedSelected;
      }
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Unable to load identity sources.'), 'ui', {
        action: 'identity_sources.refresh_list'
      });
      fetchError = appError.message;
      notifyError(appError);
    } finally {
      listLoading = false;
    }
  };

  const runTest = (payload: IdentitySourceTestPayload) => testIdentitySourceConnection(fetch, payload);

  const runTestOnSource = async (source: IdentitySourceRow) => {
    if (!source) return;
    if (identityProbeRunning(source.id)) return;

    jobsStore.startJob(identityProbeJobInput(source.id), { message: t('Probe running') });
    try {
      const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
      syncSnapshotMetaFromInternal(source.id, internal);
      const bindSecretRef = String(
        internal?.bind_password_ref ?? source.bind_password_ref ?? ''
      ).trim();

      if (source.type === 'ad' && !bindSecretRef) {
        toast.error(t('Bind secret introuvable. Configurez un bind_password_ref valide avant de lancer le test.'));
        jobsStore.failJob(identityProbeJobInput(source.id), {
          message: t('Bind secret introuvable'),
          error: t('Bind secret introuvable')
        });
        return;
      }

      const payload = {
        type: source.type,
        name: source.name,
        protocol: source.protocol,
        host: source.host,
        port: source.port,
        base_dn: source.base_dn,
        bind_dn: internal?.bind_dn ?? source.bind_dn,
        bind_password_ref: bindSecretRef,
        bind_password: null,
        issuer_url: source.issuer_url,
        client_id: source.client_id,
        client_secret_ref: internal?.client_secret_ref ?? '',
        capabilities: source.capabilities,
        is_active: source.is_active
      };
      const request = buildIdentitySourceProbeRequest({
        protocol: payload.protocol || 'ldaps',
        host: payload.host,
        port: payload.port,
        baseDn: payload.base_dn,
        bindDn: payload.bind_dn,
        secretRef: payload.bind_password_ref || undefined,
        authMode: payload?.capabilities?.auth_mode === 'kerberos' ? 'kerberos' : 'ntlm',
        identitySourceId: Number(source.id),
        uiOrigin: 'admin'
      });

      const final = await runProbeWithUi({
        fetchFn: fetch,
        request,
        intervalMs: 1500,
        maxAttempts: 30,
        onUpdate: (snapshot) => {
          const snapshotStatus = String(snapshot.status ?? '').toLowerCase();
          const status: JobStatus =
            snapshot.ok === true || snapshotStatus === 'success' || snapshotStatus === 'succeeded'
              ? 'success'
              : ['failed', 'error', 'timeout', 'timed_out', 'cancelled', 'canceled'].includes(snapshotStatus)
                ? 'error'
                : 'running';
          jobsStore.upsertJob(identityProbeJobInput(source.id), {
            status,
            ok: snapshot.ok,
            message: snapshot.status
          });
        },
        notify: toast,
        successMessage: t('Probe OK.'),
        failureMessage: ({ errorMessage }) => errorMessage ?? t('Probe failed.')
      });

      if (!final.ok) {
        jobsStore.failJob(identityProbeJobInput(source.id), {
          message: final.errorMessage ?? t('Probe failed'),
          error: final.errorMessage ?? t('Probe failed')
        });
        await loadHealthSummaryForSource(source.id, true);
        await refreshList();
        return;
      }

      jobsStore.succeedJob(identityProbeJobInput(source.id), {
        message: t('Probe OK')
      });

      const refreshed = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
      const refreshedMeta = extractSnapshotMeta(refreshed);
      syncSnapshotMetaFromInternal(source.id, refreshed);
      snapshotStore.upsert(source.id, {
        status: 'success',
        loading: false,
        error: null,
        note: t('Snapshot metadata refreshed after probe'),
        ...toSnapshotStorePatch(refreshedMeta)
      });
      patchSourceRuntimeMeta(source.id, {
        last_probe_at: String((refreshed as any)?.last_probe_at ?? '').trim() || null,
        probed_at: String((refreshed as any)?.probed_at ?? '').trim() || null,
        updated_at: String((refreshed as any)?.updated_at ?? '').trim() || null
      });
      await refreshList();
      await loadHealthSummaryForSource(source.id, true);
      if (showDetailsDrawer && selectedSourceId === source.id) {
        await loadInternal(source.id, true);
      }
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Probe impossible'), 'ui', {
        action: 'identity_sources.run_probe',
        sourceId: source.id
      });
      const message = appError.message;
      notifyError(appError);
      jobsStore.failJob(identityProbeJobInput(source.id), {
        message,
        error: message
      });
      await loadHealthSummaryForSource(source.id, true);
      await refreshList();
    }
  };

  const runSnapshotOnSource = async (source: IdentitySourceRow) => {
    if (!source) return;
    if (identitySnapshotRunning(source.id)) return;

    jobsStore.startJob(identitySnapshotJobInput(source.id), { message: t('Snapshot sync running') });
    snapshotStore.upsert(source.id, {
      status: 'running',
      loading: true,
      error: null,
      note: t('Snapshot sync running')
    });

    try {
      const run = await runIdentitySnapshot(fetch, Number(source.id), 'auto');
      const jobId = Number(run?.job_id ?? 0);
      jobsStore.upsertJob(identitySnapshotJobInput(source.id), {
        status: 'running',
        message: jobId > 0 ? t('Snapshot queued · job #{jobId}', { jobId }) : t('Snapshot queued')
      });

      if (jobId > 0) {
        const polled = await pollJobUntilTerminal(String(jobId), {
          fetchJob: (id) => getIdentityJob(fetch, Number(id)),
          getRawStatus: (job) => String(job?.status ?? ''),
          getErrorMessage: (job) => {
            const message = String(job?.error?.message ?? '').trim();
            if (message) return message;
            const code = String(job?.error?.code ?? '').trim();
            return code || undefined;
          },
          intervalMs: 1500,
          intervalMsByAttempt: (attempt) => (attempt < 2 ? 1500 : attempt < 6 ? 2500 : 4000),
          maxAttempts: 40,
          onUpdate: (status: JobUiStatus, rawJob) => {
            const nextStatus: JobStatus =
              status === 'success'
                ? 'success'
                : status === 'error' || status === 'timeout'
                  ? 'error'
                  : 'running';
            const backendStatus = String(rawJob?.status ?? '').trim().toLowerCase();
            jobsStore.upsertJob(identitySnapshotJobInput(source.id), {
              status: nextStatus,
              message: backendStatus ? t('Snapshot {backendStatus}', { backendStatus }) : t('Snapshot running')
            });
          }
        });

        if (polled.status === 'error' || polled.status === 'timeout') {
          throw new Error(polled.errorMessage ?? t('Snapshot failed'));
        }
      }

      let finalized = false;
      for (let i = 0; i < 12; i += 1) {
        const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
        const internalMeta = extractSnapshotMeta(internal);
        syncSnapshotMetaFromInternal(source.id, internal);

        const status = String(internalMeta.status ?? '').trim().toUpperCase();
        if (['FAILED', 'ERROR', 'CANCELED', 'CANCELLED'].includes(status)) {
          throw new Error(t('Snapshot {toLowerCase}.', { toLowerCase: status.toLowerCase() }));
        }

        const hasMetadata =
          Boolean(internalMeta.at) ||
          internalMeta.version !== null;
        const successStatus = ['ACTIVE', 'SUCCEEDED', 'SUCCESS'].includes(status);

        if (hasMetadata && (successStatus || i >= 2)) {
          finalized = true;
          break;
        }

        if (i < 11) await sleep(1500);
      }

      const refreshed = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
      const refreshedMeta = extractSnapshotMeta(refreshed);
      syncSnapshotMetaFromInternal(source.id, refreshed);
      const objectsCount = toFiniteCount(refreshedMeta.objects);
      const usersCount = toFiniteCount(refreshedMeta.users);
      const groupsCount = toFiniteCount(refreshedMeta.groups);
      const membershipsCount = toFiniteCount(refreshedMeta.memberships);
      const importedCount =
        objectsCount ??
        (usersCount !== null || groupsCount !== null
          ? (usersCount ?? 0) + (groupsCount ?? 0)
          : null);
      snapshotStore.upsert(source.id, {
        status: 'success',
        loading: false,
        error: null,
        note: finalized
          ? t('Snapshot metadata refreshed after snapshot sync')
          : t('Snapshot dispatched, metadata will refresh soon'),
        ...toSnapshotStorePatch(refreshedMeta)
      });
      patchSourceRuntimeMeta(source.id, {
        last_snapshot_at: String((refreshed as any)?.last_snapshot_at ?? '').trim() || null,
        snapshot_at: String((refreshed as any)?.snapshot_at ?? '').trim() || null,
        last_sync_at: String((refreshed as any)?.last_sync_at ?? '').trim() || null,
        last_snapshot_status: String((refreshed as any)?.last_snapshot_status ?? '').trim() || null,
        last_snapshot_version: toFiniteCount((refreshed as any)?.last_snapshot_version),
        last_snapshot_objects_count: toFiniteCount((refreshed as any)?.last_snapshot_objects_count),
        last_snapshot_users_count: toFiniteCount((refreshed as any)?.last_snapshot_users_count),
        last_snapshot_groups_count: toFiniteCount((refreshed as any)?.last_snapshot_groups_count),
        last_snapshot_memberships_count: toFiniteCount((refreshed as any)?.last_snapshot_memberships_count),
        updated_at: String((refreshed as any)?.updated_at ?? '').trim() || null
      });

      jobsStore.succeedJob(identitySnapshotJobInput(source.id), {
        message: finalized ? t('Snapshot synced') : t('Snapshot dispatched')
      });
      toast.success(
        finalized
          ? importedCount !== null
            ? membershipsCount !== null
              ? t('Snapshot synchronized · {importedCount} objet(s) · {membershipsCount} membership(s).', { importedCount, membershipsCount })
              : t('Snapshot synchronized · {importedCount} objet(s).', { importedCount })
            : t('Snapshot synchronized.')
          : t('Snapshot started. Synchronization in progress.')
      );
      await refreshList();
      await loadHealthSummaryForSource(source.id, true);
      if (showDetailsDrawer && selectedSourceId === source.id) {
        await loadInternal(source.id, true);
      }
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Snapshot impossible'), 'ui', {
        action: 'identity_sources.run_snapshot',
        sourceId: source.id
      });
      if (appError.code === 'SNAPSHOT_ALREADY_RUNNING') {
        // Started elsewhere (another admin, another page, the scheduler): follow it instead of failing
        jobsStore.clearJob(identitySnapshotJobInput(source.id));
        snapshotStore.upsert(source.id, { status: 'running', loading: false, error: null, note: appError.message });
        patchSourceRuntimeMeta(source.id, { snapshot_running: true });
        toast.info(appError.message);
        return;
      }
      const message = appError.message;
      notifyError(appError);
      jobsStore.failJob(identitySnapshotJobInput(source.id), {
        message,
        error: message
      });
      snapshotStore.upsert(source.id, {
        status: 'error',
        loading: false,
        error: message,
        note: null
      });
      await loadHealthSummaryForSource(source.id, true);
      await refreshList();
    }
  };

  const runCreate = async (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => {
    const protocol = (payload.protocol || 'ldaps').toLowerCase();
    const bindSecret = payload._secret ?? payload.bind_password;

    const resolved = await resolveCredentials(fetch, {
      username: payload.bind_dn ?? null,
      password: bindSecret ?? null,
      secret_ref: payload.bind_password_ref ?? null
    }, {
      secretName: `identity-source/${protocol}/${payload.host || payload.name || 'ad'}`,
      mode: 'create'
    });

    payload.bind_password_ref = resolved.secret_ref ?? payload.bind_password_ref ?? null;
    payload.bind_password = null;

    return createIdentitySource(fetch, payload);
  };

  const handleIdentityWizardDone = async () => {
    showWizard = false;
    await refreshList();
  };

  const openEdit = async (source: IdentitySourceRow) => {
    if (!source) return;
    if (!isAdIdentitySource(source)) {
      toast.error(t('Only Active Directory / LDAP identity sources can be edited in V1.'));
      return;
    }
    let sourceForEdit: IdentitySourceRow = source;
    try {
      const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceRow;
      sourceForEdit = { ...source, ...internal };
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Unable to load source metadata.'), 'ui', {
        action: 'identity_sources.open_edit',
        sourceId: source.id
      });
      notifyError(appError);
    }
    editSource = sourceForEdit;
    showEditModal = true;
  };

  const closeEdit = () => {
    showEditModal = false;
    editSource = null;
  };

  const handleEditSaved = async (id: number) => {
    await refreshList();
    if (showDetailsDrawer && selectedSourceId === id) {
      await loadInternal(id, true);
    }
  };

  const openDelete = (source: IdentitySourceRow) => {
    if (!source) return;
    if (source?.used) {
      toast.error(dependencyDeleteMessage('identity source', 'storage endpoints'));
      return;
    }
    selectionStore.setSelectedIdentitySourceId(Number(source?.id ?? 0) || null);
    selectedSource = source;
    actionError = null;
    showDeleteModal = true;
  };

  const closeDelete = () => {
    showDeleteModal = false;
    actionError = null;
    selectedSource = null;
  };

  const closeDisableUsedConfirm = () => {
    showDisableUsedConfirm = false;
    pendingToggleSource = null;
  };

  const handleToggleActive = async (source: IdentitySourceRow, nextActive: boolean) => {
    if (!source) return;
    if (!nextActive && source.used) {
      pendingToggleSource = source;
      showDisableUsedConfirm = true;
      return;
    }
    busy = true;
    actionError = null;
    try {
      await updateIdentitySource(fetch, source.id, { is_active: nextActive });
      toast.success(nextActive ? t('Source enabled.') : t('Source disabled.'));
      await refreshList();
      if (showDetailsDrawer && selectedSourceId === source.id) {
        await loadInternal(source.id, true);
      }
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Action impossible'), 'ui', {
        action: 'identity_sources.toggle_source_active',
        sourceId: source.id,
        nextActive
      });
      actionError = appError.message;
      notifyError(appError);
    } finally {
      busy = false;
    }
  };

  const confirmDisableUsedSource = async () => {
    if (!pendingToggleSource) return;
    busy = true;
    actionError = null;
    try {
      await updateIdentitySource(fetch, pendingToggleSource.id, { is_active: false });
      toast.success(t('Source disabled.'));
      closeDisableUsedConfirm();
      await refreshList();
      if (showDetailsDrawer && selectedSourceId === pendingToggleSource.id) {
        await loadInternal(pendingToggleSource.id, true);
      }
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Action impossible'), 'ui', {
        action: 'identity_sources.confirm_disable_used_source',
        sourceId: pendingToggleSource.id
      });
      actionError = appError.message;
      notifyError(appError);
    } finally {
      busy = false;
    }
  };

  const handleDelete = async () => {
    if (!selectedSource) return;
    if (selectedSource.used) {
      toast.error(dependencyDeleteMessage('identity source', 'storage endpoints'));
      closeDelete();
      return;
    }
    busy = true;
    actionError = null;
    try {
      await deleteIdentitySource(fetch, selectedSource.id);
      toast.success(t('Source deleted.'));
      if (selectedSourceId === selectedSource.id) {
        closeDetails();
      }
      closeDelete();
      await refreshList();
    } catch (e: unknown) {
      const status = e && typeof e === 'object' && 'status' in e ? Number((e as { status?: unknown }).status ?? 0) : 0;
      if (isDependencyDeleteError(e)) {
        toast.error(dependencyMessageFromError(e, dependencyDeleteMessage('identity source')));
        closeDelete();
        return;
      }
      const appError = toUiAppError(e, t('Unable to delete'), 'ui', {
        action: 'identity_sources.delete_source',
        sourceId: selectedSource.id,
        status
      });
      actionError = appError.message;
      notifyError(appError);
    } finally {
      busy = false;
    }
  };

  const closeDetails = () => {
    showDetailsDrawer = false;
    selectedSourceId = null;
    selectedInternal = null;
    internalError = null;
    snapshotDebugRows = [];
    snapshotDebugError = null;
    snapshotDebugLoading = false;
    snapshotDebugSourceId = null;
    snapshotDebugVersion = null;
    selectionStore.setSelectedIdentitySourceId(null);
  };

  const loadInternal = async (sourceId: number, force = false) => {
    if (!force && selectedInternal && Number(selectedInternal?.id ?? 0) === Number(sourceId)) return;
    internalLoading = true;
    internalError = null;
    try {
      selectedInternal = (await getIdentitySourceInternal(fetch, Number(sourceId))) as IdentitySourceInternalMeta;
      snapshotDebugVersion = toFiniteCount(selectedInternal?.last_snapshot_version ?? null);
      await loadSnapshotDebugRows(sourceId, force);
    } catch (e: unknown) {
      selectedInternal = null;
      snapshotDebugVersion = null;
      const appError = toUiAppError(e, t('Unable to load internal metadata.'), 'ui', {
        action: 'identity_sources.load_internal_metadata',
        sourceId
      });
      internalError = appError.message;
      notifyError(appError);
    } finally {
      internalLoading = false;
    }
  };

  $: hasSources = sources.length > 0;
  $: existingSourceNames = sources
    .map((s) => String(s?.name ?? s?.display_name ?? '').trim())
    .filter(Boolean);

  $: ({
    sortedCards,
    summary,
    selectedCard
  } = composeIdentitySourceCards(sources, {
    snapshotMetaBySourceId: Object.fromEntries(
      (Array.isArray(sources) ? sources : []).map((source) => {
        const sourceId = Number(source?.id ?? 0);
        return [sourceId, $snapshotStore[sourceId] ?? null] as const;
      })
    ),
    probeJobStatusBySourceId: Object.fromEntries(
      (Array.isArray(sources) ? sources : []).map((source) => {
        const sourceId = Number(source?.id ?? 0);
        return [sourceId, identityProbeJob(sourceId)?.status ?? null] as const;
      })
    ),
    snapshotJobStatusBySourceId: Object.fromEntries(
      (Array.isArray(sources) ? sources : []).map((source) => {
        const sourceId = Number(source?.id ?? 0);
        return [sourceId, identitySnapshotJob(sourceId)?.status ?? null] as const;
      })
    ),
    filters: {
      query: listQuery,
      type: typeFilter,
      status: statusFilter,
      snapshot: snapshotFilter
    },
    sortBy,
    selectedSourceId
  }));
  $: detailCard = selectedCard ?? sortedCards[0] ?? null;
  $: totalPages = Math.max(1, Math.ceil(sortedCards.length / rowsPerPage));
  $: if (currentPage > totalPages) {
    currentPage = totalPages;
  }
  $: pageStart = sortedCards.length === 0 ? 0 : (currentPage - 1) * rowsPerPage;
  $: pageEnd = Math.min(sortedCards.length, pageStart + rowsPerPage);
  $: paginatedCards = sortedCards.slice(pageStart, pageEnd);
  // Browser only: during SSR the component fetch cannot resolve relative /api URLs
  $: if (browser && detailCard?.id) {
    void loadHealthSummaryForSource(detailCard.id);
  }
  $: selectedRecentHealth = buildRecentHealth(
    detailCard,
    detailCard?.id ? healthSummaryBySourceId[detailCard.id] ?? null : null
  );

  $: if (!snapshotDebugVersion && selectedCard) {
    snapshotDebugVersion = toFiniteCount(selectedCard.raw?.last_snapshot_version ?? null);
  }

  $: if (showDetailsDrawer && selectedSourceId !== null && !selectedCard) {
    closeDetails();
  }
</script>

<section class="b2s-page b2s-page--admin identity-sources-page">
  <div class="identity-clean-shell">
    <header class="ids-head">
      <div>
        <h1>{t('Directories')}</h1>
        <p>{t('{total} directories · {healthy} healthy · {issues} with issues · {never} never synced', { total: summary.total, healthy: summary.healthy, issues: summary.issues, never: summary.neverSynced })}</p>
      </div>
      <EntityActionGroup
        ariaLabel={t('Identity source actions')}
        actions={[
        { key: 'refresh', label: t('Refresh'), icon: 'bi-arrow-clockwise', variant: 'secondary', disabled: listLoading, onClick: refreshList },
        { key: 'new', label: t('New Identity Source'), icon: 'bi-plus-lg', variant: 'primary', onClick: () => (showWizard = true) }
        ]}
      />
    </header>

    {#if fetchError}
      <InlineAlert tone="error">{fetchError}</InlineAlert>
    {/if}

    {#if !hasSources && !listLoading && !fetchError}
      <EmptyState
        containerClass="storage-endpoints-empty identity-empty-state"
        iconClass="bi bi-people"
        title={t('No identity sources yet')}
        description={t('Identity sources connect an LDAP directory to authenticate users and import identities.')}
        ctaLabel={t('Create your first identity source')}
        onCta={() => (showWizard = true)}
        hint={t('You will be guided step by step.')}
      />
    {:else}
      <div class="identity-filter-card">
        <label class="identity-search">
          <i class="bi bi-search" aria-hidden="true"></i>
          <input
            type="search"
            bind:value={listQuery}
            on:input={resetListPage}
            placeholder={t('Search identity sources...')}
            aria-label={t('Search identity sources')}
          />
        </label>
        <div class="identity-selects">
          <select bind:value={typeFilter} on:change={resetListPage} aria-label={t('Filter by type')}>
            {#each typeOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
          <select bind:value={snapshotFilter} on:change={resetListPage} aria-label={t('Filter by snapshot status')}>
            {#each snapshotOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
        </div>
        <div class="b2s-segments" role="group" aria-label={t('Health quick filters')}>
          <button type="button" class:active={statusFilter === 'all'} on:click={() => selectStatusFilter('all')}>{t('All')}</button>
          <button type="button" class:active={statusFilter === 'healthy'} on:click={() => selectStatusFilter('healthy')}>{t('Healthy')}</button>
          <button type="button" class:active={statusFilter === 'issues'} on:click={() => selectStatusFilter('issues')}>{t('Issues')}</button>
          <button type="button" class:active={statusFilter === 'disabled'} on:click={() => selectStatusFilter('disabled')}>{t('Disabled')}</button>
        </div>
        <strong class="identity-result-count">{t('{sortedCardsCount} result{value}', { sortedCardsCount: sortedCards.length, value: (sortedCards.length === 1 ? '' : 's') })}</strong>
      </div>

      {#if listLoading}
        <div class="identity-table-card" aria-busy="true">
          {#each Array(6) as _, index (`identity-loading-row-${index}`)}
            <div class="identity-row-skeleton"></div>
          {/each}
        </div>
      {:else if sortedCards.length === 0}
        <div class="identity-no-result" role="status">{t('No identity source matches current filters.')}</div>
      {:else}
        <div class="identity-table-card">
            <div class="ids-cards">
              {#each paginatedCards as card (card.id)}
                <div class="ids-card" class:selected={(selectedSourceId ?? detailCard?.id) === card.id}>
                  <button type="button" class="ids-card-main" on:click={() => selectSourceById(card.id)}>
                    <span class="ids-card-name">
                      <strong>{card.name}</strong>
                      <code>{card.endpointLabel}</code>
                    </span>
                    <span><span class={`identity-pill ${toneClass(card.typeTone)}`}>{card.typeLabel}</span></span>
                    <span class="ids-card-meta" title={card.lastProbeTitle || undefined}>
                      <small>{t('Last probe')}</small>
                      {card.lastProbeLabel}
                    </span>
                    <span><StatusBadge compact showDot={false} variant={card.snapshotTone} label={card.snapshotLabel} /></span>
                    <span><StatusBadge compact variant={card.healthTone} label={card.healthLabel} /></span>
                  </button>
                  <button
                    class="b2s-btn b2s-btn-secondary b2s-btn-sm b2s-btn-icon"
                    type="button"
                    aria-label={t('Edit {name}', { name: card.name })}
                    disabled={!isAdIdentitySource(card.raw)}
                    on:click={() => openEdit(card.raw)}
                  >
                    <i class="bi bi-three-dots-vertical" aria-hidden="true"></i>
                  </button>
                </div>
              {/each}
            </div>

            <div class="identity-table-footer">
              <label>
                {t('Rows per page:')}
                <select bind:value={rowsPerPage} on:change={resetListPage}>
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </label>
              <div class="identity-pagination">
                <span>{t('{value}–{pageEnd} of {sortedCardsCount}', { value: (pageStart + 1), pageEnd, sortedCardsCount: sortedCards.length })}</span>
                <button type="button" aria-label={t('First page')} disabled={currentPage === 1} on:click={() => goToPage(1)}>
                  <i class="bi bi-chevron-bar-left" aria-hidden="true"></i>
                </button>
                <button type="button" aria-label={t('Previous page')} disabled={currentPage === 1} on:click={() => goToPage(currentPage - 1)}>
                  <i class="bi bi-chevron-left" aria-hidden="true"></i>
                </button>
                <strong>{currentPage}</strong>
                <button type="button" aria-label={t('Next page')} disabled={currentPage === totalPages} on:click={() => goToPage(currentPage + 1)}>
                  <i class="bi bi-chevron-right" aria-hidden="true"></i>
                </button>
                <button type="button" aria-label={t('Last page')} disabled={currentPage === totalPages} on:click={() => goToPage(totalPages)}>
                  <i class="bi bi-chevron-bar-right" aria-hidden="true"></i>
                </button>
              </div>
            </div>
          </div>
      {/if}
    {/if}
  </div>
</section>

<IdentitySourceDrawer
  open={showDetailsDrawer}
  source={selectedCard}
  internal={selectedInternal}
  loading={internalLoading}
  loadError={internalError}
  snapshotDebugRows={snapshotDebugRows}
  snapshotDebugLoading={snapshotDebugLoading}
  snapshotDebugError={snapshotDebugError}
  snapshotDebugVersion={snapshotDebugVersion}
  busy={busy}
  probeRunning={selectedCard ? identityProbeRunning(selectedCard.id) : false}
  snapshotRunning={selectedCard && $jobsStore && serverSnapshotRunning ? identitySnapshotRunning(selectedCard.id) : false}
  on:close={closeDetails}
  on:refresh={() => {
    if (selectedCard) loadInternal(selectedCard.id, true);
  }}
  on:edit={() => {
    if (selectedCard) openEdit(selectedCard.raw);
  }}
  on:runProbe={() => {
    if (selectedCard) runTestOnSource(selectedCard.raw);
  }}
  on:runSnapshot={() => {
    if (selectedCard) runSnapshotOnSource(selectedCard.raw);
  }}
  on:toggle={() => {
    if (selectedCard) handleToggleActive(selectedCard.raw, !selectedCard.raw?.is_active);
  }}
  on:delete={() => {
    if (selectedCard) openDelete(selectedCard.raw);
  }}
  recentHealth={selectedRecentHealth}
/>

<IdentitySourceEditDrawer
  open={showEditModal}
  source={editSource}
  sourceCard={selectedSourceCard(editSource)}
  onClose={closeEdit}
  onSaved={handleEditSaved}
/>

<ConfirmActionModal
  open={showDeleteModal}
  onClose={closeDelete}
  ariaLabelledby="identity-delete-title"
  severity="danger"
  title={t('Delete identity source')}
  subtitle={selectedSource?.name ?? null}
  impactTitle={t('Consequences')}
  impactItems={[
    t('Irreversible deletion of this identity source.'),
    t('Authentication and identity import workflows linked to this source will stop.'),
    t('Storage endpoints must be reassigned if needed.')
  ]}
  onConfirm={handleDelete}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Delete')}
  confirmBusyLabel={t('Deleting…')}
  busy={busy}
  requireTextConfirm={true}
  requiredText=DELETE
  textConfirmLabel={t('Type')}
  textConfirmPlaceholder=DELETE
>
  <div class="identity-modal-body">
    <p>{t('This action is final. Confirm deletion.')}</p>
    {#if actionError}
      <InlineAlert tone="error">{actionError}</InlineAlert>
    {/if}
  </div>
</ConfirmActionModal>

<ConfirmActionModal
  open={showDisableUsedConfirm}
  onClose={closeDisableUsedConfirm}
  ariaLabelledby="identity-disable-used-title"
  severity="warning"
  title={t('Disable identity source')}
  subtitle={pendingToggleSource?.display_name ?? pendingToggleSource?.name ?? null}
  impactTitle={t('Consequences')}
  impactItems={[
    t('Imports linked to this source may stop.'),
    t('Authentication flows depending on this source may be impacted.')
  ]}
  onConfirm={confirmDisableUsedSource}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Disable')}
  confirmBusyLabel={t('En cours…')}
  busy={busy}
>
</ConfirmActionModal>

<IdentitySourcesWizardModal
  open={showWizard}
  onClose={() => (showWizard = false)}
  onTest={runTest}
  onCreate={runCreate}
  existingNames={existingSourceNames}
  on:done={handleIdentityWizardDone}
/>

<style>
  :global(.identity-sources-page) {
    padding: var(--b2s-page-padding);
  }

  .identity-clean-shell {
    display: grid;
    gap: 22px;
    color: var(--b2s-color-heading);
  }

  /* Filters and table on the page surface, like the other entity pages */
  .identity-clean-shell :global(.identity-filter-card),
  .identity-clean-shell :global(.identity-table-card) {
    border: 0;
    background: none;
    box-shadow: none;
  }

  .identity-clean-shell :global(.identity-filter-card) {
    min-height: 0;
    padding: 0;
  }

  .identity-clean-shell :global(.b2s-page-header) {
    margin-bottom: 2px;
  }

  .identity-page-actions {
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 14px;
    margin-left: auto;
    flex-wrap: wrap;
  }
  .identity-pagination button {
    font-family: var(--b2s-font-sans);
    letter-spacing: 0;
  }

  .identity-filter-card {
    min-height: 80px;
    display: grid;
    grid-template-columns: minmax(260px, 330px) auto 1fr auto;
    gap: 20px;
    align-items: center;
    padding: 16px 20px;
  }

  .identity-search {
    height: 42px;
    display: flex;
    align-items: center;
    gap: 10px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    padding: 0 14px;
    color: #48607f;
  }

  .identity-search input {
    width: 100%;
    border: 0;
    outline: 0;
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-md);
    background: transparent;
  }

  .identity-search input::placeholder {
    color: #72829a;
  }

  .identity-selects {
    display: inline-flex;
    align-items: center;
    gap: 12px;
  }

  .identity-selects select,
  .identity-table-footer select {
    min-width: 112px;
    height: 42px;
    border-radius: var(--b2s-radius-sm);
    border: 1px solid var(--b2s-color-border-soft);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-heading);
    padding: 0 34px 0 14px;
    font-weight: 550;
    font-size: var(--b2s-fs-md);
  }

  .identity-result-count {
    color: var(--b2s-color-heading);
    font-size: var(--b2s-fs-md);
    font-weight: 650;
    white-space: nowrap;
  }

  .identity-table-card {
    overflow: hidden;
  }

  .identity-clean-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: var(--b2s-fs-md);
  }

  .identity-source-cell {
    display: flex;
    align-items: center;
    gap: 13px;
    min-width: 0;
  }

  .identity-source-mini {
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #0b63f4;
  }

  .identity-muted-cell {
    color: #5e6f89;
  }

  .identity-pill {
    min-height: 25px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    max-width: 100%;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid #d7e0ee;
    background: var(--b2s-color-surface-soft);
    color: #425473;
    padding: 3px 9px;
    font-size: var(--b2s-fs-xs);
    line-height: 1.1;
    font-weight: 600;
    white-space: nowrap;
  }

  .identity-pill.is-success,
  .identity-health-label.is-success{
    color: #0b8f49;
  }

  .identity-pill.is-success {
    background: var(--b2s-color-success-soft);
    border-color: #a7e8bd;
  }

  .identity-pill.is-warning,
  .identity-health-label.is-warning{
    color: var(--b2s-color-warning-strong);
  }

  .identity-pill.is-warning {
    background: var(--b2s-color-warning-soft);
    border-color: var(--b2s-color-warning-border);
  }

  .identity-pill.is-error,
  .identity-health-label.is-error{
    color: var(--b2s-color-danger);
  }

  .identity-pill.is-error {
    background: var(--b2s-color-danger-soft);
    border-color: var(--b2s-color-danger-border);
  }

  .identity-pill.is-info,
  .identity-pill.is-ad,
  .identity-pill.is-oidc {
    color: #0758d8;
    background: var(--b2s-color-info-soft);
    border-color: #b8d2ff;
  }

  .identity-pill.is-disabled,
  .identity-pill.is-muted {
    color: var(--b2s-color-text-soft);
    background: var(--b2s-color-surface-soft);
    border-color: var(--b2s-color-border-mid);
  }

  .identity-health-label {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #596985;
    font-weight: 550;
  }

  .identity-table-footer {
    min-height: 70px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    padding: 14px 16px;
    border-top: 1px solid #dce4ef;
  }

  .identity-table-footer label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #51637e;
    font-size: var(--b2s-fs-sm);
  }

  .identity-table-footer select {
    min-width: 80px;
  }

  .identity-pagination {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    color: #51637e;
  }

  .identity-pagination button,
  .identity-pagination strong {
    width: 34px;
    height: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    border: 1px solid transparent;
    background: transparent;
    color: #536885;
  }

  .identity-pagination strong {
    background: var(--b2s-color-heading);
    color: #ffffff;
    font-weight: 650;
  }

  .identity-pagination button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .identity-row-skeleton {
    height: 66px;
    margin: 14px;
    border-radius: var(--b2s-radius-sm);
    background: linear-gradient(90deg, rgba(148, 163, 184, 0.18), rgba(148, 163, 184, 0.34), rgba(148, 163, 184, 0.18));
    background-size: 200% 100%;
    animation: identity-loading 1.4s ease-in-out infinite;
  }

  .identity-row-skeleton.small {
    height: 38px;
  }

  .identity-no-result {
    padding: 1rem;
    border-radius: var(--b2s-radius-sm);
    border: 1px dashed rgba(148, 163, 184, 0.45);
    color: var(--b2s-color-text-muted);
    background: rgba(248, 250, 252, 0.75);
    text-align: center;
    font-size: var(--b2s-fs-md);
  }

  @keyframes identity-loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }


  .identity-sources-page :global(h1) {
    font-size: 38px;
    line-height: 1.05;
    font-weight: 600;
    letter-spacing: -.03em;
  }

  .ids-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
  .ids-head p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .ids-cards { display: flex; flex-direction: column; gap: 10px; }
  .ids-card { display: flex; align-items: center; gap: 12px; padding-right: 16px; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: 16px; }
  .ids-card:hover { box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .ids-card.selected { border-color: var(--b2s-color-text); box-shadow: 0 0 0 1px var(--b2s-color-text); }
  .ids-card-main { flex: 1; min-width: 0; display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr) 130px minmax(0, 1fr) 100px; gap: 14px; align-items: center; padding: 16px; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .ids-card-name strong { display: block; font-size: 16px; font-weight: 600; }
  .ids-card-name code { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); }
  .ids-card-meta small { display: block; font-size: 12px; color: var(--b2s-color-text-muted); }
</style>
