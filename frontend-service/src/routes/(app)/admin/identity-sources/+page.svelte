<script lang="ts">
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t, intlLocale } from '$lib/i18n';
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { onDestroy } from 'svelte';
  import { sleep } from '$lib/utils/values';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import EntityWorkspace from '$lib/components/entity/EntityWorkspace.svelte';
  import IdentitySourcesSidebar from '$lib/components/identity-sources/IdentitySourcesSidebar.svelte';
  import IdentitySourceWorkspace from '$lib/components/identity-sources/IdentitySourceWorkspace.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { page } from '$app/stores';
  import IdentitySourceEditDrawer from '$lib/components/identity-sources/IdentitySourceEditDrawer.svelte';
  import {
    browseIdentitySource,
    deleteIdentitySource,
    getIdentitySourceInternal,
    listIdentitySources,
    runIdentitySnapshot,
    updateIdentitySource,
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

  export let data: {
    identity_sources?: IdentitySourceRow[];
    fetch_error?: string | null;
  };

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
        toast.error(t('The password of the account is missing: enter it again before testing.'));
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
        tls_verify: source.tls_verify,
        tls_ca_pem: source.tls_ca_pem,
        tls_server_name: source.tls_server_name,
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
        tlsVerify: payload.tls_verify,
        tlsCaPem: payload.tls_ca_pem,
        tlsServerName: payload.tls_server_name,
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
    selectionStore.setSelectedIdentitySourceId(null);
  };

  const loadInternal = async (sourceId: number, force = false) => {
    if (!force && selectedInternal && Number(selectedInternal?.id ?? 0) === Number(sourceId)) return;
    internalLoading = true;
    internalError = null;
    try {
      selectedInternal = (await getIdentitySourceInternal(fetch, Number(sourceId))) as IdentitySourceInternalMeta;
    } catch (e: unknown) {
      selectedInternal = null;
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

  // The page opens on a directory: ?selected=, else the first by name. Placed before the cards are composed:
  // a reactive statement does not run again for a value changed by a later one.
  let sidebarQuery = '';
  $: if (browser && selectedSourceId === null && sources.length) {
    const wanted = Number($page.url.searchParams.get('selected') ?? 0);
    const byName = [...sources].sort((x, y) => String(x?.name ?? '').localeCompare(String(y?.name ?? ''), 'fr'));
    const first = sources.find((source) => Number(source?.id ?? 0) === wanted) ?? byName[0];
    selectSourceById(Number(first?.id ?? 0));
  }

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

  // A deleted directory: the page opens on another one
  $: if (selectedSourceId !== null && sources.length && !sources.some((source) => Number(source?.id ?? 0) === selectedSourceId)) {
    selectedSourceId = null;
  }

  $: if (browser && selectedSourceId !== null && Number($page.url.searchParams.get('selected') ?? 0) !== selectedSourceId) {
    const next = new URL($page.url);
    next.searchParams.set('selected', String(selectedSourceId));
    goto(`${next.pathname}${next.search}`, { replaceState: true, noScroll: true, keepFocus: true });
  }
</script>

{#if !hasSources && !listLoading && !fetchError}
  <section class="b2s-page b2s-page--admin">
    <EmptyState
      page
      containerClass="identity-empty-state"
      iconClass="bi bi-people"
      title={t('No identity sources yet')}
      description={t('Identity sources connect an LDAP directory to authenticate users and import identities.')}
      ctaLabel={t('Create your first identity source')}
      onCta={() => goto('/admin/identity-sources/new')}
      hint={t('You will be guided step by step.')}
    />
  </section>
{:else}
  <EntityWorkspace title={t('Directories')} contentKey={selectedSourceId}>
    <svelte:fragment slot="list">
      <IdentitySourcesSidebar
        cards={sortedCards}
        selectedId={selectedSourceId}
        query={sidebarQuery}
        onQueryChange={(value) => (sidebarQuery = value)}
        onSelect={selectSourceById}
        onAdd={() => goto('/admin/identity-sources/new')}
      />
    </svelte:fragment>
    {#if fetchError}<InlineAlert tone="error">{fetchError}</InlineAlert>{/if}
    {#if selectedCard}
      <IdentitySourceWorkspace
        card={selectedCard}
        internal={selectedInternal}
        {busy}
        probeRunning={identityProbeRunning(selectedCard.id)}
        snapshotRunning={$jobsStore && serverSnapshotRunning ? identitySnapshotRunning(selectedCard.id) : false}
        onEdit={() => selectedCard && openEdit(selectedCard.raw)}
        onTest={() => selectedCard && runTestOnSource(selectedCard.raw)}
        onSync={() => selectedCard && runSnapshotOnSource(selectedCard.raw)}
        onToggle={() => selectedCard && handleToggleActive(selectedCard.raw, !selectedCard.raw?.is_active)}
        onDelete={() => selectedCard && openDelete(selectedCard.raw)}
      />
    {:else}
      <LoadingState block skeleton="detail" />
    {/if}
  </EntityWorkspace>
{/if}

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
  requiredText={String(selectedSource?.name ?? '')}
  textConfirmLabel={t('Type the name to confirm')}
  textConfirmPlaceholder={String(selectedSource?.name ?? '')}
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
  confirmBusyLabel={t('In progress…')}
  busy={busy}
>
</ConfirmActionModal>

<style>
  .identity-modal-body { display: flex; flex-direction: column; gap: 10px; }
</style>
