<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import ConfirmActionModal from '$lib/components/common/ConfirmActionModal.svelte';
  import IdentitySourcesWizardModal from '$lib/components/identity-sources/IdentitySourcesWizardModal.svelte';
  import EmptyStateCard from '$lib/components/common/EmptyStateCard.svelte';
  import IdentitySourceDrawer from '$lib/components/identity-sources/IdentitySourceDrawer.svelte';
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
    formatAbsoluteTimestamp,
    formatRelativeTimestamp,
    identitySourceTypeLabel,
    type IdentitySourceCardVM,
    type IdentitySourceSortKey
  } from '$lib/services/mappers/identity-sources.mapper';
  import { buildIdentitySourceProbeRequest } from '$lib/probe/probe-runner';
  import { runProbeWithUi } from '$lib/probe/probe-ui';
  import { resolveCredentials } from '$lib/auth/credentials-service';
  import { toast } from '$lib/utils/toast';
  import { dependencyDeleteMessage, isDependencyDeleteError } from '$lib/utils/delete-guard';
  import { notifyError, toAppError, type AppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
  import {
    extractSnapshotMeta,
    toSnapshotStorePatch,
    toFiniteCount,
    type IdentitySourceInternalMeta
  } from '$lib/services/identity-sources.helpers';
  import { pollJobUntilTerminal } from '$lib/features/jobs/polling';
  import type { JobUiStatus } from '$lib/features/jobs/types';
  import { jobsStore, type JobStatus } from '$lib/stores/app/jobs.store';
  import { selectionStore } from '$lib/stores/app/selection.store';
  import { snapshotStore } from '$lib/stores/features/snapshot.store';

  type IdentitySourceRow = {
    id: number;
    type?: string;
    name?: string;
    display_name?: string;
    protocol?: 'ldap' | 'ldaps' | string;
    host?: string;
    port?: number;
    base_dn?: string;
    bind_dn?: string;
    bind_password_ref?: string;
    issuer_url?: string;
    client_id?: string;
    status?: string;
    is_active?: boolean;
    used?: boolean;
    last_probe_at?: string | null;
    probed_at?: string | null;
    last_probe_message?: string | null;
    last_snapshot_at?: string | null;
    snapshot_at?: string | null;
    last_sync_at?: string | null;
    last_snapshot_status?: string | null;
    last_snapshot_version?: number | null;
    last_snapshot_objects_count?: number | null;
    last_snapshot_users_count?: number | null;
    last_snapshot_groups_count?: number | null;
    last_snapshot_memberships_count?: number | null;
    capabilities?: {
      auth?: boolean;
      import_groups?: boolean;
      auth_mode?: 'ntlm' | 'kerberos' | string;
      snapshot_enabled?: boolean;
    };
    updated_at?: string | null;
  };

  type IdentitySourceUpdateDraft = {
    type: string;
    name: string;
    protocol: string | null;
    host: string | null;
    port: number | null;
    base_dn: string | null;
    bind_dn: string | null;
    bind_password_ref: string | null;
    bind_password: string | null;
    issuer_url: string | null;
    client_id: string | null;
    capabilities: {
      auth: boolean;
      import_groups: boolean;
      snapshot_enabled: boolean;
    };
    is_active: boolean;
    client_secret?: string;
  };

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
  let showBindPasswordRef = false;
  let showClientSecret = false;
  let showEditErrors = false;
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
  let editProbeRunning = false;
  let editProbeResult: {
    ok: boolean;
    message: string;
    status?: string | null;
    jobId?: string | number | null;
    result?: Record<string, unknown> | null;
    checkedAt?: string | null;
  } | null = null;

  let editForm = {
    type: 'ad',
    name: '',
    display_name: '',
    protocol: 'ldaps',
    host: '',
    port: 636,
    base_dn: '',
    bind_dn: '',
    bind_password_ref: '',
    bind_password: '',
    issuer_url: '',
    client_id: '',
    client_secret: '',
    capabilities: { auth: true, import_groups: true, snapshot_enabled: false },
    is_active: true
  };

  let sources: IdentitySourceRow[] = data.identity_sources ?? [];

  const typeOptions = [
    { value: 'all', label: 'Type' },
    { value: 'ad', label: 'Active Directory / LDAP' },
    { value: 'oidc', label: 'OIDC' },
    { value: 'local', label: 'Local' }
  ];

  const healthOptions = [
    { value: 'all', label: 'Health' },
    { value: 'healthy', label: 'Healthy' },
    { value: 'issues', label: 'Issues' },
    { value: 'disabled', label: 'Disabled' },
    { value: 'unknown', label: 'Unknown' }
  ];

  const snapshotOptions = [
    { value: 'all', label: 'Snapshots' },
    { value: 'synced', label: 'Synced' },
    { value: 'never', label: 'Never synced' },
    { value: 'failed', label: 'Failed' },
    { value: 'running', label: 'Running' }
  ];

  const toneClass = (tone: string | null | undefined): string => {
    const normalized = String(tone ?? '').trim().toLowerCase();
    if (normalized === 'success') return 'is-success';
    if (normalized === 'warning') return 'is-warning';
    if (normalized === 'error') return 'is-error';
    if (normalized === 'info') return 'is-info';
    if (normalized === 'ad') return 'is-ad';
    if (normalized === 'oidc') return 'is-oidc';
    if (normalized === 'disabled') return 'is-disabled';
    return 'is-muted';
  };

  const sourceIconClass = (card: IdentitySourceCardVM | null): string => {
    const type = String(card?.raw?.type ?? '').trim().toLowerCase();
    if (type === 'oidc') return 'bi-shield-check';
    if (type === 'local') return 'bi-people';
    return 'bi-diagram-3';
  };

  const isAdIdentitySource = (source: IdentitySourceRow | null | undefined): boolean => {
    const type = String(source?.type ?? '').trim().toLowerCase();
    return type === 'ad' || type === 'ldap';
  };

  const compactProbeLabel = (card: IdentitySourceCardVM | null): string => {
    if (!card) return '—';
    if (!card.supportsProbe) return 'Not applicable';
    return card.lastProbeLabel || 'Never';
  };

  const compactSnapshotLabel = (card: IdentitySourceCardVM | null): string => {
    if (!card) return '—';
    if (!card.supportsSnapshot) return 'Not applicable';
    return card.lastSnapshotLabel || 'No snapshot yet';
  };

  const lastSyncLabel = (source: IdentitySourceRow | null | undefined): string => {
    const raw = String(source?.last_snapshot_at ?? '').trim();
    if (raw) return formatRelativeTimestamp(raw);
    return source?.capabilities?.snapshot_enabled ? 'Never synced' : 'Not applicable';
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

  const editSourceCard = (): IdentitySourceCardVM | null => selectedSourceCard(selectedSource);

  const editEndpointLabel = (): string => {
    const source = selectedSource;
    if (!source) return '—';
    const host = String(editForm.host || source.host || '').trim();
    const issuer = String(editForm.issuer_url || source.issuer_url || '').trim();
    const port = Number(editForm.port || source.port || 0);
    if (host) return `${host}${Number.isFinite(port) && port > 0 ? `:${port}` : ''}`;
    if (issuer) return issuer;
    return '—';
  };

  const editHealthLabel = (): string => {
    if (editProbeRunning) return 'Checking';
    if (editProbeResult) return editProbeResult.ok ? 'Healthy' : 'Unhealthy';
    return editSourceCard()?.healthLabel ?? 'Unknown';
  };

  const editHealthTone = (): string => {
    if (editProbeRunning) return 'info';
    if (editProbeResult) return editProbeResult.ok ? 'success' : 'error';
    return editSourceCard()?.healthTone ?? 'muted';
  };

  const validationCheckedLabel = (): string => {
    if (editProbeRunning) return 'Testing now';
    const checked = editProbeResult?.checkedAt ?? selectedSource?.last_probe_at ?? null;
    if (!checked) return 'No test yet';
    return `Last tested ${formatRelativeTimestamp(checked)}`;
  };

  const probeResultValue = (keys: string[]): unknown => {
    const result = editProbeResult?.result;
    if (!result || typeof result !== 'object') return undefined;
    for (const key of keys) {
      if (key in result) return result[key];
    }
    return undefined;
  };

  const validationChecks = () => {
    const status = String(editProbeResult?.status ?? selectedSource?.status ?? '').trim().toLowerCase();
    const lastMessage = String(editProbeResult?.message ?? selectedSource?.last_probe_message ?? '').trim();
    const ok =
      editProbeResult?.ok ??
      ['active', 'healthy', 'connected', 'online', 'success', 'succeeded'].includes(status);
    const bindOk = probeResultValue(['bind_ok', 'ldap_bind_ok', 'auth_ok']);
    const tlsOk = probeResultValue(['tls_ok', 'certificate_ok', 'cert_ok']);
    const duration = probeResultValue(['duration_ms', 'response_time_ms', 'elapsed_ms']);

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
        title:
          bindOk === true
            ? 'LDAP bind succeeded'
            : bindOk === false
              ? 'LDAP bind failed'
              : 'LDAP bind',
        description:
          bindOk === true
            ? 'The service account bind was successful.'
            : bindOk === false
              ? 'The service account bind failed.'
              : 'Not reported by the latest probe.',
        tone: bindOk === false ? 'error' : bindOk === true ? 'success' : 'muted',
        icon: bindOk === false ? 'bi-x-lg' : bindOk === true ? 'bi-check-lg' : 'bi-dash'
      },
      {
        key: 'certificate',
        title:
          String(editForm.protocol).toLowerCase() === 'ldaps'
            ? tlsOk === true
              ? 'Server certificate valid'
              : tlsOk === false
                ? 'Server certificate invalid'
                : 'Server certificate'
            : 'TLS certificate',
        description:
          String(editForm.protocol).toLowerCase() !== 'ldaps'
            ? 'Not applicable for LDAP.'
            : tlsOk === true
              ? 'The server certificate is trusted and valid.'
              : tlsOk === false
                ? 'The server certificate could not be validated.'
                : 'Not reported by the latest probe.',
        tone:
          String(editForm.protocol).toLowerCase() !== 'ldaps'
            ? 'muted'
            : tlsOk === false
              ? 'error'
              : tlsOk === true
                ? 'success'
                : 'muted',
        icon:
          String(editForm.protocol).toLowerCase() !== 'ldaps'
            ? 'bi-dash'
            : tlsOk === false
              ? 'bi-x-lg'
              : tlsOk === true
                ? 'bi-check-lg'
                : 'bi-dash'
      },
      {
        key: 'response',
        title: 'Response time',
        description:
          duration !== undefined && duration !== null && String(duration).trim()
            ? `${String(duration).trim()} ms`
            : 'Not reported by the latest probe.',
        tone: 'muted',
        icon: 'bi-speedometer2'
      }
    ];
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
    if (index === total - 1) return 'Today';
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleDateString('en-US', {
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
          `${String(row.status ?? 'unknown')} · ${Number(row.checks ?? 0)} check${Number(row.checks ?? 0) === 1 ? '' : 's'}`,
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
            ? 'Today'
            : date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric'
              }),
        tone: 'is-muted',
        title: healthSummaryLoadingSourceId === card.id ? 'Loading health history' : 'No health check history',
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
    showDetailsDrawer = false;
    selectedInternal = null;
    internalError = null;
    snapshotDebugRows = [];
    snapshotDebugError = null;
    snapshotDebugSourceId = null;
    selectionStore.setSelectedIdentitySourceId(id);
  };

  $: if (Array.isArray(data?.identity_sources)) {
    sources = data.identity_sources;
  }

  $: if (typeof data?.fetch_error === 'string') {
    fetchError = data.fetch_error;
  }

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
      const appError = normalizeIdentityError(e, 'Unable to load snapshot debug rows.', 'ui', {
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

  const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

  const normalizeIdentityError = (
    error: unknown,
    fallback: string,
    source: AppError['source'],
    context?: Record<string, unknown>
  ): AppError => {
    const normalized = toAppError(error, { source });
    const appError = GENERIC_ERROR_MESSAGES.has(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
    logAppError(appError, context);
    return appError;
  };

  const dependencyMessageFromError = (error: unknown, fallback: string): string => {
    const appError = toAppError(error, { source: 'ui' });
    const message = String(appError.message ?? '').trim();
    return GENERIC_ERROR_MESSAGES.has(message) || !message ? fallback : message;
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

  const identitySnapshotRunning = (sourceId: number) =>
    identitySnapshotJob(sourceId)?.status === 'running';

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
      const appError = normalizeIdentityError(e, 'Unable to load identity sources.', 'ui', {
        action: 'identity_sources.refresh_list'
      });
      fetchError = appError.message;
      notifyError(appError);
    } finally {
      listLoading = false;
    }
  };

  const runTest = async (payload: IdentitySourcePayload & { _secret?: string; bind_password?: string | null }) => {
    const protocol = (payload.protocol || 'ldaps').toLowerCase();
    const authMode = payload?.capabilities?.auth_mode ?? 'ntlm';

    let secretRef: string | undefined = payload.bind_password_ref || undefined;
    const bindSecret = payload._secret ?? payload.bind_password;

    if (!secretRef && bindSecret) {
      try {
        const resolved = await resolveCredentials(fetch, {
          username: payload.bind_dn ?? null,
          password: bindSecret ?? null,
          secret_ref: payload.bind_password_ref ?? null
        }, { secretName: `identity-source/${protocol}/${payload.host || 'ad'}`, mode: 'create' });
        secretRef = resolved.secret_ref ?? null;
      } catch (e: unknown) {
        const appError = normalizeIdentityError(e, 'Unable to store secret.', 'auth', {
          action: 'identity_sources.resolve_bind_secret'
        });
        notifyError(appError);
        throw appError;
      }
    }

    if (!secretRef && payload.bind_dn) {
      toast.error('Password is required to test the connection (no secret_ref available).');
      throw new Error('Missing secret_ref for bind_dn');
    }

    const request = buildIdentitySourceProbeRequest({
      protocol,
      host: payload.host,
      port: payload.port,
      baseDn: payload.base_dn,
      bindDn: payload.bind_dn,
      secretRef,
      authMode,
      uiOrigin: 'wizard'
    });

    const finalStatus = await runProbeWithUi({
      fetchFn: fetch,
      request,
      intervalMs: 1500,
      maxAttempts: 30
    });
    const ok = Boolean(finalStatus?.ok ?? finalStatus?.result?.success === true);
    return {
      ok,
      checks: [
        {
          key: 'probe',
          ok,
          message: finalStatus?.result?.message || finalStatus?.errorMessage || (ok ? 'Probe OK' : 'Probe failed')
        }
      ],
      status: finalStatus?.status,
      job_id: finalStatus?.jobId
    };
  };

  const runTestOnSource = async (source: IdentitySourceRow) => {
    if (!source) return;
    if (identityProbeRunning(source.id)) return;

    jobsStore.startJob(identityProbeJobInput(source.id), { message: 'Probe running' });
    try {
      const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
      syncSnapshotMetaFromInternal(source.id, internal);
      const bindSecretRef = String(
        internal?.bind_password_ref ?? source.bind_password_ref ?? ''
      ).trim();

      if (source.type === 'ad' && !bindSecretRef) {
        toast.error('Bind secret introuvable. Configurez un bind_password_ref valide avant de lancer le probe.');
        jobsStore.failJob(identityProbeJobInput(source.id), {
          message: 'Bind secret introuvable',
          error: 'Bind secret introuvable'
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
        authMode: payload?.capabilities?.auth_mode ?? 'ntlm',
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
        successMessage: 'Probe OK.',
        failureMessage: ({ errorMessage }) => errorMessage ?? 'Probe failed.'
      });

      if (!final.ok) {
        jobsStore.failJob(identityProbeJobInput(source.id), {
          message: final.errorMessage ?? 'Probe failed',
          error: final.errorMessage ?? 'Probe failed'
        });
        await loadHealthSummaryForSource(source.id, true);
        await refreshList();
        return;
      }

      jobsStore.succeedJob(identityProbeJobInput(source.id), {
        message: 'Probe OK'
      });

      const refreshed = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
      const refreshedMeta = extractSnapshotMeta(refreshed);
      syncSnapshotMetaFromInternal(source.id, refreshed);
      snapshotStore.upsert(source.id, {
        status: 'success',
        loading: false,
        error: null,
        note: 'Snapshot metadata refreshed after probe',
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
      const appError = normalizeIdentityError(e, 'Probe impossible', 'ui', {
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

    jobsStore.startJob(identitySnapshotJobInput(source.id), { message: 'Snapshot sync running' });
    snapshotStore.upsert(source.id, {
      status: 'running',
      loading: true,
      error: null,
      note: 'Snapshot sync running'
    });

    try {
      const run = await runIdentitySnapshot(fetch, Number(source.id), 'auto');
      const jobId = Number(run?.job_id ?? 0);
      jobsStore.upsertJob(identitySnapshotJobInput(source.id), {
        status: 'running',
        message: jobId > 0 ? `Snapshot queued · job #${jobId}` : 'Snapshot queued'
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
              message: backendStatus ? `Snapshot ${backendStatus}` : 'Snapshot running'
            });
          }
        });

        if (polled.status === 'error' || polled.status === 'timeout') {
          throw new Error(polled.errorMessage ?? 'Snapshot failed');
        }
      }

      let finalized = false;
      for (let i = 0; i < 12; i += 1) {
        const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceInternalMeta;
        const internalMeta = extractSnapshotMeta(internal);
        syncSnapshotMetaFromInternal(source.id, internal);

        const status = String(internalMeta.status ?? '').trim().toUpperCase();
        if (['FAILED', 'ERROR', 'CANCELED', 'CANCELLED'].includes(status)) {
          throw new Error(`Snapshot ${status.toLowerCase()}.`);
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
          ? 'Snapshot metadata refreshed after snapshot sync'
          : 'Snapshot dispatched, metadata will refresh soon',
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
        message: finalized ? 'Snapshot synced' : 'Snapshot dispatched'
      });
      toast.success(
        finalized
          ? importedCount !== null
            ? membershipsCount !== null
              ? `Snapshot synchronized · ${importedCount} objet(s) · ${membershipsCount} membership(s).`
              : `Snapshot synchronized · ${importedCount} objet(s).`
            : 'Snapshot synchronized.'
          : 'Snapshot started. Synchronization in progress.'
      );
      await refreshList();
      await loadHealthSummaryForSource(source.id, true);
      if (showDetailsDrawer && selectedSourceId === source.id) {
        await loadInternal(source.id, true);
      }
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Snapshot impossible', 'ui', {
        action: 'identity_sources.run_snapshot',
        sourceId: source.id
      });
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
      const hint = appError.code
        ? `Code: ${String(appError.code)}${appError.requestId ? ` · requestId: ${String(appError.requestId)}` : ''}`
        : appError.requestId
          ? `requestId: ${String(appError.requestId)}`
          : null;
      toast.error(hint ? `${message} (${hint})` : message);
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
      toast.error('Only Active Directory / LDAP identity sources can be edited in V1.');
      return;
    }
    let sourceForEdit: IdentitySourceRow = source;
    try {
      const internal = (await getIdentitySourceInternal(fetch, Number(source.id))) as IdentitySourceRow;
      sourceForEdit = { ...source, ...internal };
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Unable to load source metadata.', 'ui', {
        action: 'identity_sources.open_edit',
        sourceId: source.id
      });
      notifyError(appError);
    }
    const sourceDisplayName = (sourceForEdit?.display_name ?? sourceForEdit?.name ?? '').trim();
    selectedSource = sourceForEdit;
    editForm = {
      type: sourceForEdit?.type ?? 'ad',
      name: sourceForEdit?.name ?? sourceDisplayName,
      display_name: sourceDisplayName,
      protocol: sourceForEdit?.protocol ?? 'ldaps',
      host: sourceForEdit?.host ?? '',
      port: sourceForEdit?.port ?? (sourceForEdit?.protocol === 'ldap' ? 389 : 636),
      base_dn: sourceForEdit?.base_dn ?? '',
      bind_dn: sourceForEdit?.bind_dn ?? '',
      bind_password_ref: sourceForEdit?.bind_password_ref ?? '',
      bind_password: '',
      issuer_url: sourceForEdit?.issuer_url ?? '',
      client_id: sourceForEdit?.client_id ?? '',
      client_secret: '',
      capabilities: {
        auth: sourceForEdit?.capabilities?.auth ?? true,
        import_groups: sourceForEdit?.capabilities?.import_groups ?? true,
        snapshot_enabled: sourceForEdit?.capabilities?.snapshot_enabled ?? false
      },
      is_active: sourceForEdit?.is_active ?? true
    };
    showBindPasswordRef = false;
    showClientSecret = false;
    showEditErrors = false;
    editProbeResult = null;
    editProbeRunning = false;
    actionError = null;
    showEditModal = true;
  };

  const _normalize = (value: unknown) => String(value ?? '').trim();
  const _effectiveEditName = () => _normalize(editForm.display_name) || _normalize(editForm.name);

  const _hasEditChanges = () => {
    const src = selectedSource;
    if (!src) return false;

    if (editForm.type === 'ad') {
      return (
        _effectiveEditName() !== _normalize(src.display_name ?? src.name) ||
        _normalize(editForm.protocol) !== _normalize(src.protocol || 'ldaps') ||
        _normalize(editForm.host) !== _normalize(src.host) ||
        Number(editForm.port) !== Number(src.port || (src.protocol === 'ldap' ? 389 : 636)) ||
        _normalize(editForm.base_dn) !== _normalize(src.base_dn) ||
        _normalize(editForm.bind_dn) !== _normalize(src.bind_dn) ||
        _normalize(editForm.bind_password_ref) !== _normalize(src.bind_password_ref) ||
        _normalize(editForm.bind_password) !== '' ||
        !!editForm.capabilities.auth !== !!(src.capabilities?.auth ?? true) ||
        !!editForm.capabilities.import_groups !== !!(src.capabilities?.import_groups ?? true) ||
        !!editForm.capabilities.snapshot_enabled !== !!(src.capabilities?.snapshot_enabled ?? false) ||
        !!editForm.is_active !== !!(src.is_active ?? true)
      );
    }

    return (
      _effectiveEditName() !== _normalize(src.display_name ?? src.name) ||
      _normalize(editForm.issuer_url) !== _normalize(src.issuer_url) ||
      _normalize(editForm.client_id) !== _normalize(src.client_id) ||
      _normalize(editForm.client_secret) !== '' ||
      !!editForm.capabilities.auth !== !!(src.capabilities?.auth ?? true) ||
      !!editForm.capabilities.import_groups !== !!(src.capabilities?.import_groups ?? true) ||
      !!editForm.capabilities.snapshot_enabled !== !!(src.capabilities?.snapshot_enabled ?? false) ||
      !!editForm.is_active !== !!(src.is_active ?? true)
    );
  };

  const closeEdit = () => {
    showEditModal = false;
    actionError = null;
    selectedSource = null;
    editProbeResult = null;
    editProbeRunning = false;
    showEditErrors = false;
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

  const setEditProtocol = (value: 'ldap' | 'ldaps') => {
    editForm.protocol = value;
    editForm.port = value === 'ldaps' ? 636 : 389;
  };

  let adRequiredOk = false;
  let oidcRequiredOk = false;
  let canSave = false;

  $: adRequiredOk =
    !!_effectiveEditName() &&
    !!editForm.host.trim() &&
    !!editForm.base_dn.trim() &&
    !!editForm.bind_dn.trim();

  $: oidcRequiredOk =
    !!_effectiveEditName() &&
    !!editForm.issuer_url.trim() &&
    !!editForm.client_id.trim();

  $: canSave =
    (editForm.type === 'ad' ? adRequiredOk : oidcRequiredOk) && _hasEditChanges();

  const handleSave = async () => {
    if (!selectedSource) return;
    if (!canSave) {
      showEditErrors = true;
      actionError = 'Please fill in required fields.';
      return;
    }
    busy = true;
    actionError = null;
    try {
      let payload: IdentitySourceUpdateDraft = {
        type: editForm.type,
        name: _effectiveEditName(),
        protocol: editForm.type === 'ad' ? editForm.protocol : null,
        host: editForm.type === 'ad' ? editForm.host.trim() || null : null,
        port: editForm.type === 'ad' ? (editForm.port ? Number(editForm.port) : null) : null,
        base_dn: editForm.type === 'ad' ? editForm.base_dn.trim() || null : null,
        bind_dn: editForm.type === 'ad' ? editForm.bind_dn.trim() || null : null,
        bind_password_ref: editForm.type === 'ad' ? editForm.bind_password_ref.trim() || null : null,
        bind_password: editForm.type === 'ad' ? editForm.bind_password.trim() || null : null,
        issuer_url: editForm.type === 'oidc' ? editForm.issuer_url.trim() || null : null,
        client_id: editForm.type === 'oidc' ? editForm.client_id.trim() || null : null,
        capabilities: {
          auth: !!editForm.capabilities.auth,
          import_groups: !!editForm.capabilities.import_groups,
          snapshot_enabled: !!editForm.capabilities.snapshot_enabled
        },
        is_active: !!editForm.is_active
      };

      if (editForm.type === 'oidc' && editForm.client_secret) {
        payload.client_secret = editForm.client_secret;
      }

      if (payload.type === 'ad' && !payload.bind_password_ref && payload.bind_password) {
        const protocol = (payload.protocol || 'ldaps').toLowerCase();
        const resolved = await resolveCredentials(fetch, {
          username: payload.bind_dn ?? null,
          password: payload.bind_password ?? null,
          secret_ref: payload.bind_password_ref ?? null
        }, { secretName: `identity-source/${protocol}/${payload.host || payload.name || 'ad'}`, mode: 'create' });
        payload.bind_password_ref = resolved.secret_ref ?? payload.bind_password_ref ?? null;
        payload.bind_password = null;
      }

      await updateIdentitySource(fetch, selectedSource.id, payload as Partial<IdentitySourcePayload>);
      toast.success('Source updated.');
      closeEdit();
      await refreshList();
      if (showDetailsDrawer && selectedSourceId === selectedSource.id) {
        await loadInternal(selectedSource.id, true);
      }
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Unable to update', 'ui', {
        action: 'identity_sources.update_source',
        sourceId: selectedSource.id
      });
      actionError = appError.message;
      notifyError(appError);
    } finally {
      busy = false;
    }
  };

  const handleEditTestConnection = async () => {
    if (!selectedSource) return;
    const isAd = editForm.type === 'ad';
    if (isAd && (!editForm.host.trim() || !editForm.base_dn.trim() || !editForm.bind_dn.trim())) {
      showEditErrors = true;
      actionError = 'Please fill in required fields before testing.';
      return;
    }
    if (!isAd && (!editForm.issuer_url.trim() || !editForm.client_id.trim())) {
      showEditErrors = true;
      actionError = 'Please fill in required fields before testing.';
      return;
    }

    editProbeRunning = true;
    actionError = null;
    editProbeResult = null;
    try {
      const payload = {
        type: editForm.type,
        name: _effectiveEditName(),
        protocol: editForm.protocol,
        host: editForm.host.trim() || null,
        port: editForm.port ? Number(editForm.port) : null,
        base_dn: editForm.base_dn.trim() || null,
        bind_dn: editForm.bind_dn.trim() || null,
        bind_password_ref: editForm.bind_password_ref.trim() || selectedSource.bind_password_ref || null,
        bind_password: editForm.bind_password.trim() || null,
        issuer_url: editForm.issuer_url.trim() || null,
        client_id: editForm.client_id.trim() || null,
        capabilities: {
          auth: !!editForm.capabilities.auth,
          import_groups: !!editForm.capabilities.import_groups,
          snapshot_enabled: !!editForm.capabilities.snapshot_enabled,
          auth_mode: selectedSource.capabilities?.auth_mode ?? 'ntlm'
        },
        is_active: !!editForm.is_active
      } as IdentitySourcePayload & { bind_password?: string | null };

      const result = await runTest(payload);
      const firstCheck = Array.isArray(result?.checks) ? result.checks[0] : null;
      editProbeResult = {
        ok: Boolean(result?.ok),
        status: result?.status ?? null,
        jobId: result?.job_id ?? null,
        message:
          String(firstCheck?.message ?? '').trim() ||
          (result?.ok ? 'Probe OK' : 'Probe failed'),
        result: null,
        checkedAt: new Date().toISOString()
      };
      if (result?.ok) {
        toast.success('Connection validated.');
      } else {
        toast.error(editProbeResult.message);
      }
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Connection test failed.', 'ui', {
        action: 'identity_sources.edit_test_connection',
        sourceId: selectedSource.id
      });
      editProbeResult = {
        ok: false,
        status: 'failed',
        message: appError.message,
        result: null,
        checkedAt: new Date().toISOString()
      };
      notifyError(appError);
    } finally {
      editProbeRunning = false;
    }
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
      toast.success(nextActive ? 'Source enabled.' : 'Source disabled.');
      await refreshList();
      if (showDetailsDrawer && selectedSourceId === source.id) {
        await loadInternal(source.id, true);
      }
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Action impossible', 'ui', {
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
      toast.success('Source disabled.');
      closeDisableUsedConfirm();
      await refreshList();
      if (showDetailsDrawer && selectedSourceId === pendingToggleSource.id) {
        await loadInternal(pendingToggleSource.id, true);
      }
    } catch (e: unknown) {
      const appError = normalizeIdentityError(e, 'Action impossible', 'ui', {
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
      toast.success('Source deleted.');
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
      const appError = normalizeIdentityError(e, 'Unable to delete', 'ui', {
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
      const appError = normalizeIdentityError(e, 'Unable to load internal metadata.', 'ui', {
        action: 'identity_sources.load_internal_metadata',
        sourceId
      });
      internalError = appError.message;
      notifyError(appError);
    } finally {
      internalLoading = false;
    }
  };

  const openDetailsById = async (sourceId: number) => {
    const id = Number(sourceId ?? 0);
    if (!Number.isFinite(id) || id <= 0) return;
    selectedSourceId = id;
    showDetailsDrawer = true;
    selectionStore.setSelectedIdentitySourceId(id);
    await loadInternal(id, true);
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
  $: if (detailCard?.id) {
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
    <PageHeader title="Identity Sources" subtitle="Manage LDAP / OIDC identity sources and monitor operational health.">
      <svelte:fragment slot="actions">
        <div class="identity-page-actions">
          <button class="identity-cta" type="button" on:click={() => (showWizard = true)}>
            <i class="bi bi-plus-lg" aria-hidden="true"></i>
            New Identity Source
          </button>
          <button class="identity-cta ghost" type="button" on:click={refreshList} disabled={listLoading}>
            <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
            Refresh
          </button>
        </div>
      </svelte:fragment>
    </PageHeader>

    {#if fetchError}
      <div class="identity-fetch-error" role="alert">
        <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
        <span>{fetchError}</span>
      </div>
    {/if}

    {#if !hasSources && !listLoading && !fetchError}
      <EmptyStateCard
        containerClass="storage-endpoints-empty identity-empty-state"
        iconClass="bi bi-people"
        title="No identity sources yet"
        description="Identity sources let you connect LDAP or OIDC providers to authenticate users and import identities into BornToShare."
        ctaLabel="Create your first identity source"
        onCta={() => (showWizard = true)}
        hint="The wizard will guide you step by step."
      />
    {:else}
      <div class="identity-kpi-grid" aria-label="Identity source summary">
        <article class="identity-kpi-card">
          <div class="identity-kpi-icon is-info"><i class="bi bi-diagram-3" aria-hidden="true"></i></div>
          <div>
            <span>Sources</span>
            <strong>{summary.total}</strong>
          </div>
        </article>
        <article class="identity-kpi-card">
          <div class="identity-kpi-icon is-success"><i class="bi bi-check-lg" aria-hidden="true"></i></div>
          <div>
            <span>Healthy</span>
            <strong>{summary.healthy}</strong>
          </div>
        </article>
        <article class="identity-kpi-card">
          <div class="identity-kpi-icon is-warning"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i></div>
          <div>
            <span>Issues</span>
            <strong>{summary.issues}</strong>
          </div>
        </article>
        <article class="identity-kpi-card">
          <div class="identity-kpi-icon is-purple"><i class="bi bi-clock" aria-hidden="true"></i></div>
          <div>
            <span>Never synced</span>
            <strong>{summary.neverSynced}</strong>
          </div>
        </article>
      </div>

      <div class="identity-filter-card">
        <label class="identity-search">
          <i class="bi bi-search" aria-hidden="true"></i>
          <input
            type="search"
            bind:value={listQuery}
            on:input={resetListPage}
            placeholder="Search identity sources..."
            aria-label="Search identity sources"
          />
        </label>
        <div class="identity-selects">
          <select bind:value={typeFilter} on:change={resetListPage} aria-label="Filter by type">
            {#each typeOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
          <select bind:value={statusFilter} on:change={resetListPage} aria-label="Filter by health">
            {#each healthOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
          <select bind:value={snapshotFilter} on:change={resetListPage} aria-label="Filter by snapshot status">
            {#each snapshotOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
        </div>
        <div class="identity-status-tabs" role="group" aria-label="Health quick filters">
          <button type="button" class:active={statusFilter === 'all'} on:click={() => selectStatusFilter('all')}>All</button>
          <button type="button" class:active={statusFilter === 'healthy'} on:click={() => selectStatusFilter('healthy')}>Healthy</button>
          <button type="button" class:active={statusFilter === 'issues'} on:click={() => selectStatusFilter('issues')}>Issues</button>
          <button type="button" class:active={statusFilter === 'disabled'} on:click={() => selectStatusFilter('disabled')}>Disabled</button>
        </div>
        <strong class="identity-result-count">{sortedCards.length} result{sortedCards.length === 1 ? '' : 's'}</strong>
      </div>

      {#if listLoading}
        <div class="identity-main-grid" aria-busy="true">
          <div class="identity-table-card">
            {#each Array(6) as _, index (`identity-loading-row-${index}`)}
              <div class="identity-row-skeleton"></div>
            {/each}
          </div>
          <div class="identity-detail-card identity-detail-card--empty">
            <div class="identity-row-skeleton"></div>
            <div class="identity-row-skeleton small"></div>
            <div class="identity-row-skeleton"></div>
          </div>
        </div>
      {:else if sortedCards.length === 0}
        <div class="identity-no-result" role="status">No identity source matches current filters.</div>
      {:else}
        <div class="identity-main-grid">
          <div class="identity-table-card">
            <table class="identity-clean-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Endpoint</th>
                  <th>Health</th>
                  <th>Last probe</th>
                  <th>Snapshot</th>
                  <th class="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                {#each paginatedCards as card (card.id)}
                  <tr
                    class:selected={(selectedSourceId ?? detailCard?.id) === card.id}
                    on:click={() => selectSourceById(card.id)}
                  >
                    <td>
                      <div class="identity-source-cell">
                        <span class={`identity-source-mini ${toneClass(card.typeTone)}`}>
                          <i class={`bi ${sourceIconClass(card)}`} aria-hidden="true"></i>
                        </span>
                        <strong>{card.name}</strong>
                      </div>
                    </td>
                    <td><span class={`identity-pill ${toneClass(card.typeTone)}`}>{card.typeLabel}</span></td>
                    <td class="identity-muted-cell">{card.endpointLabel}</td>
                    <td>
                      <span class={`identity-health-label ${toneClass(card.healthTone)}`}>
                        <i class="bi bi-circle-fill" aria-hidden="true"></i>
                        {card.healthLabel}
                      </span>
                    </td>
                    <td>{card.lastProbeLabel}</td>
                    <td><span class={`identity-pill ${toneClass(card.snapshotTone)}`}>{card.snapshotLabel}</span></td>
                    <td class="text-end">
                      <button
                        class="identity-icon-btn"
                        type="button"
                        aria-label={`Edit ${card.name}`}
                        disabled={!isAdIdentitySource(card.raw)}
                        on:click|stopPropagation={() => openEdit(card.raw)}
                      >
                        <i class="bi bi-three-dots-vertical" aria-hidden="true"></i>
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>

            <div class="identity-table-footer">
              <label>
                Rows per page:
                <select bind:value={rowsPerPage} on:change={resetListPage}>
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </label>
              <div class="identity-pagination">
                <span>{pageStart + 1}&ndash;{pageEnd} of {sortedCards.length}</span>
                <button type="button" aria-label="First page" disabled={currentPage === 1} on:click={() => goToPage(1)}>
                  <i class="bi bi-chevron-bar-left" aria-hidden="true"></i>
                </button>
                <button type="button" aria-label="Previous page" disabled={currentPage === 1} on:click={() => goToPage(currentPage - 1)}>
                  <i class="bi bi-chevron-left" aria-hidden="true"></i>
                </button>
                <strong>{currentPage}</strong>
                <button type="button" aria-label="Next page" disabled={currentPage === totalPages} on:click={() => goToPage(currentPage + 1)}>
                  <i class="bi bi-chevron-right" aria-hidden="true"></i>
                </button>
                <button type="button" aria-label="Last page" disabled={currentPage === totalPages} on:click={() => goToPage(totalPages)}>
                  <i class="bi bi-chevron-bar-right" aria-hidden="true"></i>
                </button>
              </div>
            </div>
          </div>

          <aside class="identity-detail-card">
            {#if detailCard}
              <div class="identity-detail-head">
                <span class="identity-detail-icon">
                  <i class={`bi ${sourceIconClass(detailCard)}`} aria-hidden="true"></i>
                </span>
                <div>
                  <h2>{detailCard.name}</h2>
                  <div class="identity-detail-badges">
                    <span class={`identity-pill ${toneClass(detailCard.typeTone)}`}>{detailCard.typeLabel}</span>
                    <span class={`identity-pill ${toneClass(detailCard.healthTone)}`}>
                      <i class="bi bi-circle-fill" aria-hidden="true"></i>
                      {detailCard.healthLabel}
                    </span>
                  </div>
                </div>
              </div>

              <dl class="identity-detail-list">
                <div>
                  <dt>Endpoint</dt>
                  <dd>{detailCard.endpointLabel}</dd>
                </div>
                <div>
                  <dt>Base DN</dt>
                  <dd>{baseDnLabel(detailCard)}</dd>
                </div>
                <div>
                  <dt>Last probe</dt>
                  <dd>{compactProbeLabel(detailCard)}</dd>
                </div>
                <div>
                  <dt>Snapshot</dt>
                  <dd><span class={`identity-pill ${toneClass(detailCard.snapshotTone)}`}>{compactSnapshotLabel(detailCard)}</span></dd>
                </div>
              </dl>

              <div class="identity-detail-actions">
                {#if detailCard.supportsProbe}
                  <button
                    type="button"
                    class="identity-secondary-btn"
                    disabled={identityProbeRunning(detailCard.id)}
                    on:click={() => runTestOnSource(detailCard.raw)}
                  >
                    <i class="bi bi-activity" aria-hidden="true"></i>
                    Test connection
                  </button>
                {/if}
                <button type="button" class="identity-secondary-btn" disabled={!isAdIdentitySource(detailCard.raw)} on:click={() => openEdit(detailCard.raw)}>
                  <i class="bi bi-pencil" aria-hidden="true"></i>
                  Edit
                </button>
                <button type="button" class="identity-danger-btn" on:click={() => openDelete(detailCard.raw)}>
                  <i class="bi bi-trash3" aria-hidden="true"></i>
                  Delete
                </button>
                {#if detailCard.supportsSnapshot}
                  <button
                    type="button"
                    class="identity-primary-btn"
                    disabled={identitySnapshotRunning(detailCard.id)}
                    on:click={() => runSnapshotOnSource(detailCard.raw)}
                  >
                    <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
                    Sync now
                  </button>
                {/if}
              </div>

              <div class="identity-health-card">
                <div class="identity-health-head">
                  <h3>Recent health</h3>
                  <span>Last 7 days</span>
                </div>
                <div class="identity-health-line" aria-label="Recent health status">
                  {#each selectedRecentHealth as point (point.key)}
                    <div class="identity-health-point">
                      <span class={`identity-health-dot ${point.tone}`} title={point.title}>
                        <i class={`bi ${point.icon}`} aria-hidden="true"></i>
                      </span>
                      <small>{point.label}</small>
                    </div>
                  {/each}
                </div>
              </div>

            {/if}
          </aside>
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
  snapshotRunning={selectedCard ? identitySnapshotRunning(selectedCard.id) : false}
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
/>

<Drawer
  open={showEditModal}
  width="760px"
  showHeader={false}
  rootClass="identity-edit-drawer"
  panelClass="identity-edit-drawer__panel"
  contentClass="identity-edit-drawer__content"
  footerClass="identity-edit-drawer__footer"
  onClose={closeEdit}
>
  <div class="identity-edit-shell">
    <header class="identity-edit-header">
      <div class="identity-edit-title-row">
        <span class="identity-edit-icon">
          <i class={`bi ${sourceIconClass(editSourceCard())}`} aria-hidden="true"></i>
        </span>
        <div class="identity-edit-title">
          <h2>Edit identity source</h2>
          <p>{selectedSource?.display_name ?? selectedSource?.name ?? 'Identity source'}</p>
          <div class="identity-edit-badges">
            <span class={`identity-pill ${editForm.is_active ? 'is-success' : 'is-disabled'}`}>
              <i class="bi bi-circle-fill" aria-hidden="true"></i>
              {editForm.is_active ? 'Active' : 'Disabled'}
            </span>
            {#if selectedSource?.used}
              <span class="identity-pill is-info">
                <i class="bi bi-circle-fill" aria-hidden="true"></i>
                In use
              </span>
            {/if}
          </div>
        </div>
      </div>
      <button type="button" class="identity-edit-close" aria-label="Close" on:click={closeEdit}>
        <i class="bi bi-x-lg" aria-hidden="true"></i>
      </button>
    </header>

    <section class="identity-edit-summary" aria-label="Identity source summary">
      <div>
        <span>Type</span>
        <strong>{editSourceCard()?.typeLabel ?? identitySourceTypeLabel(editForm.type)}</strong>
      </div>
      <div>
        <span>Endpoint</span>
        <strong>{editEndpointLabel()}</strong>
      </div>
      <div>
        <span>Status</span>
        <strong class={`identity-edit-status ${toneClass(editHealthTone())}`}>
          <i class="bi bi-circle-fill" aria-hidden="true"></i>
          {editHealthLabel()}
        </strong>
      </div>
      <div>
        <span>Last sync</span>
        <strong>{lastSyncLabel(selectedSource)}</strong>
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
          <input class={`identity-edit-input ${showEditErrors && !_effectiveEditName() ? 'is-invalid' : ''}`} bind:value={editForm.display_name} />
          {#if showEditErrors && !_effectiveEditName()}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        {#if editForm.type === 'ad'}
          <label class="identity-edit-field">
            <span>Protocol</span>
            <div class="identity-edit-segmented" role="group" aria-label="LDAP protocol">
              <button type="button" class:active={editForm.protocol === 'ldap'} on:click={() => setEditProtocol('ldap')}>LDAP</button>
              <button type="button" class:active={editForm.protocol === 'ldaps'} on:click={() => setEditProtocol('ldaps')}>LDAPS</button>
            </div>
          </label>
          <label class="identity-edit-field">
            <span>Hostname / IP</span>
            <input class={`identity-edit-input ${showEditErrors && !editForm.host.trim() ? 'is-invalid' : ''}`} bind:value={editForm.host} />
            {#if showEditErrors && !editForm.host.trim()}
              <small class="identity-field-error">Required</small>
            {/if}
          </label>
          <label class="identity-edit-field">
            <span>Port</span>
            <input class="identity-edit-input" type="number" min="1" max="65535" bind:value={editForm.port} />
          </label>
          <label class="identity-edit-field identity-edit-field--full">
            <span>Base DN</span>
            <input class={`identity-edit-input ${showEditErrors && !editForm.base_dn.trim() ? 'is-invalid' : ''}`} bind:value={editForm.base_dn} />
            {#if showEditErrors && !editForm.base_dn.trim()}
              <small class="identity-field-error">Required</small>
            {/if}
          </label>
          <div class="identity-edit-note identity-edit-field--full">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
            {editForm.protocol === 'ldaps'
              ? 'LDAPS selected: port set to 636 automatically.'
              : 'LDAP selected: port set to 389 automatically.'}
          </div>
        {:else}
          <label class="identity-edit-field identity-edit-field--full">
            <span>Issuer URL</span>
            <input class={`identity-edit-input ${showEditErrors && !editForm.issuer_url.trim() ? 'is-invalid' : ''}`} bind:value={editForm.issuer_url} />
            {#if showEditErrors && !editForm.issuer_url.trim()}
              <small class="identity-field-error">Required</small>
            {/if}
          </label>
          <label class="identity-edit-field identity-edit-field--full">
            <span>Client ID</span>
            <input class={`identity-edit-input ${showEditErrors && !editForm.client_id.trim() ? 'is-invalid' : ''}`} bind:value={editForm.client_id} />
            {#if showEditErrors && !editForm.client_id.trim()}
              <small class="identity-field-error">Required</small>
            {/if}
          </label>
        {/if}
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
          <input class={`identity-edit-input ${showEditErrors && editForm.type === 'ad' && !editForm.bind_dn.trim() ? 'is-invalid' : ''}`} bind:value={editForm.bind_dn} disabled={editForm.type !== 'ad'} />
          {#if showEditErrors && editForm.type === 'ad' && !editForm.bind_dn.trim()}
            <small class="identity-field-error">Required</small>
          {/if}
        </label>
        <label class="identity-edit-field">
          <span>Bind password</span>
          <div class="identity-edit-input-action">
            <input
              class="identity-edit-input"
              type={showBindPasswordRef ? 'text' : 'password'}
              bind:value={editForm.bind_password}
              placeholder={editForm.bind_password_ref ? 'Stored secret unchanged' : 'AD account password'}
              disabled={editForm.type !== 'ad'}
            />
            <button
              type="button"
              aria-label={showBindPasswordRef ? 'Hide password' : 'Show password'}
              on:click={() => (showBindPasswordRef = !showBindPasswordRef)}
              disabled={editForm.type !== 'ad'}
            >
              <i class={`bi ${showBindPasswordRef ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
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
          <input type="checkbox" bind:checked={editForm.capabilities.auth} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-diagram-3" aria-hidden="true"></i></span>
          <span>
            <strong>Import groups</strong>
            <small>Import groups from this source.</small>
          </span>
          <input type="checkbox" bind:checked={editForm.capabilities.import_groups} />
        </label>
        <label class="identity-edit-capability">
          <span class="identity-edit-capability-icon"><i class="bi bi-shield-check" aria-hidden="true"></i></span>
          <span>
            <strong>Source active</strong>
            <small>Enable this source across the system.</small>
          </span>
          <input type="checkbox" bind:checked={editForm.is_active} />
        </label>
      </div>
    </section>

    <section class="identity-edit-card">
      <div class="identity-edit-section-head identity-edit-section-head--inline">
        <div>
          <h3>Validation</h3>
          <p>Results from the most recent connection test.</p>
        </div>
        <span class={`identity-edit-tested ${toneClass(editHealthTone())}`}>
          <i class="bi bi-circle-fill" aria-hidden="true"></i>
          {validationCheckedLabel()}
        </span>
      </div>
      <div class={`identity-edit-validation ${editProbeResult?.ok === false ? 'is-error' : editProbeResult?.ok === true ? 'is-success' : ''}`}>
        {#each validationChecks() as check (check.key)}
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

    <button type="button" class="identity-edit-advanced">
      <span>Advanced settings</span>
      <i class="bi bi-chevron-down" aria-hidden="true"></i>
    </button>

    {#if actionError}
      <div class="identity-error">{actionError}</div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="identity-edit-footer-state">
      <strong>{canSave ? 'Unsaved changes' : 'No unsaved changes'}</strong>
      <span class={editProbeResult?.ok === false ? 'is-error' : 'is-success'}>
        <i class="bi bi-circle-fill" aria-hidden="true"></i>
        {validationCheckedLabel()}
      </span>
    </div>
    <div class="identity-edit-drawer-footer">
      <button type="button" class="identity-btn ghost" on:click={closeEdit} disabled={busy || editProbeRunning}>Cancel</button>
      <button type="button" class="identity-btn outline" on:click={handleEditTestConnection} disabled={busy || editProbeRunning}>
        {editProbeRunning ? 'Testing…' : 'Test connection'}
      </button>
      <button type="button" class="identity-btn primary" on:click={handleSave} disabled={busy || !canSave || editProbeRunning}>
        {busy ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

<ConfirmActionModal
  open={showDeleteModal}
  onClose={closeDelete}
  ariaLabelledby="identity-delete-title"
  severity="danger"
  title="Delete identity source"
  subtitle={selectedSource?.name ?? null}
  impactTitle="Consequences"
  impactItems={[
    'Irreversible deletion of this identity source.',
    'Authentication and identity import workflows linked to this source will stop.',
    'Storage endpoints must be reassigned if needed.'
  ]}
  onConfirm={handleDelete}
  cancelLabel="Cancel"
  confirmLabel="Delete"
  confirmBusyLabel="Deleting…"
  busy={busy}
  requireTextConfirm={true}
  requiredText="DELETE"
  textConfirmLabel="Type"
  textConfirmPlaceholder="DELETE"
>
  <div class="identity-modal-body">
    <p>This action is final. Confirm deletion.</p>
    {#if actionError}
      <div class="identity-error">{actionError}</div>
    {/if}
  </div>
</ConfirmActionModal>

<ConfirmActionModal
  open={showDisableUsedConfirm}
  onClose={closeDisableUsedConfirm}
  ariaLabelledby="identity-disable-used-title"
  severity="warning"
  title="Disable identity source"
  subtitle={pendingToggleSource?.display_name ?? pendingToggleSource?.name ?? null}
  impactTitle="Consequences"
  impactItems={[
    'Imports linked to this source may stop.',
    'Authentication flows depending on this source may be impacted.'
  ]}
  onConfirm={confirmDisableUsedSource}
  cancelLabel="Cancel"
  confirmLabel="Disable"
  confirmBusyLabel="En cours…"
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
    background: #f7faff;
    padding: 26px 36px 34px;
  }

  .identity-clean-shell {
    display: grid;
    gap: 22px;
    color: #071638;
  }

  .identity-clean-shell :global(.b2s-page-header) {
    margin-bottom: 2px;
  }

  .identity-clean-shell :global(.b2s-page-header h1) {
    font-size: 2rem;
    line-height: 1.1;
    font-weight: 500;
    letter-spacing: 0;
    color: #071638;
  }

  .identity-clean-shell :global(.b2s-page-header p) {
    color: #596985;
    font-size: 0.98rem;
  }

  .identity-clean-shell :global(.b2s-page-header__main) {
    width: 100%;
  }

  .identity-clean-shell :global(.b2s-page-header__actions) {
    margin-left: auto;
  }

  .identity-page-actions {
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 14px;
    margin-left: auto;
    flex-wrap: wrap;
  }

  .identity-cta,
  .identity-primary-btn,
  .identity-secondary-btn,
  .identity-icon-btn,
  .identity-danger-btn,
  .identity-status-tabs button,
  .identity-pagination button {
    font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
    letter-spacing: 0;
  }

  .identity-cta {
    min-height: 46px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    border: 1px solid rgba(5, 20, 55, 0.14);
    border-radius: 7px;
    padding: 0 18px;
    color: #ffffff;
    background: #071638;
    box-shadow: 0 10px 20px rgba(7, 22, 56, 0.18);
    font-size: 0.91rem;
    font-weight: 650;
  }

  .identity-cta.ghost {
    background: #ffffff;
    color: #071638;
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
    border-color: #d5deeb;
  }

  .identity-cta:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .identity-cta:disabled {
    opacity: 0.62;
    cursor: not-allowed;
  }

  .identity-fetch-error {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.62rem 0.75rem;
    border-radius: 8px;
    border: 1px solid rgba(185, 28, 28, 0.24);
    background: rgba(254, 242, 242, 0.86);
    color: #991b1b;
    font-size: 0.86rem;
    font-weight: 600;
  }

  .identity-kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 22px;
  }

  .identity-kpi-card,
  .identity-filter-card,
  .identity-table-card,
  .identity-detail-card {
    background: #ffffff;
    border: 1px solid #dbe3ef;
    border-radius: 8px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  }

  .identity-kpi-card {
    min-height: 88px;
    display: flex;
    align-items: center;
    gap: 22px;
    padding: 18px 28px;
  }

  .identity-kpi-card span {
    display: block;
    color: #596985;
    font-size: 1rem;
    line-height: 1.2;
  }

  .identity-kpi-card strong {
    display: block;
    margin-top: 3px;
    color: #071638;
    font-size: 1.45rem;
    line-height: 1;
    font-weight: 650;
  }

  .identity-kpi-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    font-size: 1.35rem;
  }

  .identity-kpi-icon.is-info { color: #0b63f4; }
  .identity-kpi-icon.is-success {
    color: #0ca152;
    font-size: 1.25rem;
  }
  .identity-kpi-icon.is-warning { color: #ea580c; }
  .identity-kpi-icon.is-purple {
    color: #7048e8;
    font-size: 1.2rem;
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
    border: 1px solid #d9e2ef;
    border-radius: 7px;
    background: #ffffff;
    padding: 0 14px;
    color: #48607f;
  }

  .identity-search input {
    width: 100%;
    border: 0;
    outline: 0;
    color: #071638;
    font-size: 0.9rem;
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
    border-radius: 7px;
    border: 1px solid #d9e2ef;
    background: #ffffff;
    color: #071638;
    padding: 0 34px 0 14px;
    font-weight: 550;
    font-size: 0.86rem;
  }

  .identity-status-tabs {
    justify-self: end;
    display: inline-grid;
    grid-template-columns: repeat(4, minmax(86px, 1fr));
    border: 1px solid #d9e2ef;
    border-radius: 7px;
    overflow: hidden;
    background: #f8fafc;
  }

  .identity-status-tabs button {
    height: 42px;
    border: 0;
    border-right: 1px solid #d9e2ef;
    background: transparent;
    color: #596985;
    font-size: 0.86rem;
    font-weight: 500;
  }

  .identity-status-tabs button:last-child {
    border-right: 0;
  }

  .identity-status-tabs button.active {
    position: relative;
    background: #ffffff;
    color: #071638;
    font-weight: 650;
  }

  .identity-status-tabs button.active::after {
    content: "";
    position: absolute;
    left: 20%;
    right: 20%;
    bottom: 0;
    height: 3px;
    border-radius: 999px 999px 0 0;
    background: #071638;
  }

  .identity-result-count {
    color: #071638;
    font-size: 0.9rem;
    font-weight: 650;
    white-space: nowrap;
  }

  .identity-main-grid {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(360px, 0.98fr);
    gap: 20px;
    align-items: start;
  }

  .identity-table-card {
    overflow: hidden;
  }

  .identity-clean-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 0.86rem;
  }

  .identity-clean-table th {
    padding: 18px 16px;
    color: #253b5f;
    font-size: 0.72rem;
    font-weight: 650;
    text-transform: uppercase;
    border-bottom: 1px solid #dce4ef;
    white-space: nowrap;
  }

  .identity-clean-table td {
    height: 66px;
    padding: 12px 16px;
    color: #071638;
    border-bottom: 1px solid #dce4ef;
    vertical-align: middle;
  }

  .identity-clean-table tbody tr {
    cursor: pointer;
    transition: background 0.14s ease;
  }

  .identity-clean-table tbody tr:hover,
  .identity-clean-table tbody tr.selected {
    background: #eef5ff;
  }

  .identity-clean-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .identity-source-cell {
    display: flex;
    align-items: center;
    gap: 13px;
    min-width: 0;
  }

  .identity-source-cell strong {
    min-width: 0;
    color: #071638;
    font-weight: 650;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
    border-radius: 999px;
    border: 1px solid #d7e0ee;
    background: #f8fafc;
    color: #425473;
    padding: 3px 9px;
    font-size: 0.78rem;
    line-height: 1.1;
    font-weight: 600;
    white-space: nowrap;
  }

  .identity-pill.is-success,
  .identity-health-label.is-success,
  .identity-health-dot.is-success {
    color: #0b8f49;
  }

  .identity-pill.is-success {
    background: #dcfce7;
    border-color: #a7e8bd;
  }

  .identity-pill.is-warning,
  .identity-health-label.is-warning,
  .identity-health-dot.is-warning {
    color: #b45309;
  }

  .identity-pill.is-warning {
    background: #fff7ed;
    border-color: #fed7aa;
  }

  .identity-pill.is-error,
  .identity-health-label.is-error,
  .identity-health-dot.is-error {
    color: #dc2626;
  }

  .identity-pill.is-error {
    background: #fef2f2;
    border-color: #fecaca;
  }

  .identity-pill.is-info,
  .identity-pill.is-ad,
  .identity-pill.is-oidc {
    color: #0758d8;
    background: #eff6ff;
    border-color: #b8d2ff;
  }

  .identity-pill.is-disabled,
  .identity-pill.is-muted {
    color: #475569;
    background: #f8fafc;
    border-color: #cbd5e1;
  }

  .identity-health-label {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #596985;
    font-weight: 550;
  }

  .identity-health-label i,
  .identity-pill i {
    font-size: 0.5rem;
  }

  .identity-icon-btn {
    width: 32px;
    height: 32px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: #071638;
  }

  .identity-icon-btn:hover {
    background: #eaf1fb;
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
    font-size: 0.84rem;
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
    border-radius: 7px;
    border: 1px solid transparent;
    background: transparent;
    color: #536885;
  }

  .identity-pagination strong {
    background: #071638;
    color: #ffffff;
    font-weight: 650;
  }

  .identity-pagination button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .identity-detail-card {
    padding: 22px 26px 0;
    overflow: hidden;
  }

  .identity-detail-head {
    display: flex;
    align-items: flex-start;
    gap: 18px;
    margin-bottom: 22px;
  }

  .identity-detail-icon {
    flex: 0 0 auto;
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #0b63f4;
    font-size: 1.35rem;
  }

  .identity-detail-head h2 {
    margin: 0 0 10px;
    color: #071638;
    font-size: 1.32rem;
    line-height: 1.15;
    font-weight: 650;
  }

  .identity-detail-badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .identity-detail-list {
    display: grid;
    gap: 14px;
    margin: 0 0 22px;
  }

  .identity-detail-list div {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    gap: 14px;
    align-items: start;
  }

  .identity-detail-list dt {
    color: #5b6d86;
    font-weight: 500;
  }

  .identity-detail-list dd {
    margin: 0;
    min-width: 0;
    color: #071638;
    font-weight: 550;
    overflow-wrap: anywhere;
  }

  .identity-detail-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }

  .identity-secondary-btn,
  .identity-primary-btn,
  .identity-danger-btn {
    min-height: 42px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    border-radius: 7px;
    padding: 0 14px;
    font-size: 0.86rem;
    font-weight: 650;
    white-space: nowrap;
  }

  .identity-secondary-btn {
    border: 1px solid #d5deeb;
    background: #ffffff;
    color: #071638;
  }

  .identity-primary-btn {
    border: 1px solid #071638;
    background: #071638;
    color: #ffffff;
    box-shadow: 0 10px 18px rgba(7, 22, 56, 0.16);
  }

  .identity-danger-btn {
    border: 1px solid #fecaca;
    background: #fff7f7;
    color: #b42318;
  }

  .identity-secondary-btn:disabled,
  .identity-primary-btn:disabled,
  .identity-danger-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    box-shadow: none;
  }

  .identity-health-card {
    border-top: 1px solid #dce4ef;
    padding: 20px 0 18px;
  }

  .identity-health-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 22px;
  }

  .identity-health-head h3 {
    margin: 0;
    color: #071638;
    font-size: 1rem;
    font-weight: 650;
  }

  .identity-health-head span {
    color: #596985;
    font-size: 0.8rem;
    font-weight: 500;
  }

  .identity-health-line {
    position: relative;
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 4px;
  }

  .identity-health-line::before {
    content: "";
    position: absolute;
    left: 7%;
    right: 7%;
    top: 11px;
    height: 3px;
    background: #16a34a;
    border-radius: 999px;
  }

  .identity-health-point {
    position: relative;
    z-index: 1;
    display: grid;
    justify-items: center;
    gap: 8px;
  }

  .identity-health-dot {
    width: 22px;
    height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: currentColor;
    color: #16a34a;
  }

  .identity-health-dot i {
    color: #ffffff;
    font-size: 0.78rem;
  }

  .identity-health-dot.is-warning {
    color: #f59e0b;
  }

  .identity-health-dot.is-error {
    color: #dc2626;
  }

  .identity-health-dot.is-info {
    color: #2563eb;
  }

  .identity-health-dot.is-muted,
  .identity-health-dot.is-disabled {
    color: #94a3b8;
  }

  .identity-health-line:has(.identity-health-dot.is-error)::before,
  .identity-health-line:has(.identity-health-dot.is-warning)::before,
  .identity-health-line:has(.identity-health-dot.is-info)::before,
  .identity-health-line:has(.identity-health-dot.is-muted)::before,
  .identity-health-line:has(.identity-health-dot.is-disabled)::before {
    background: #cbd5e1;
  }

  .identity-health-point small {
    color: #071638;
    font-size: 0.76rem;
    white-space: nowrap;
  }

  .identity-row-skeleton {
    height: 66px;
    margin: 14px;
    border-radius: 8px;
    background: linear-gradient(90deg, rgba(148, 163, 184, 0.18), rgba(148, 163, 184, 0.34), rgba(148, 163, 184, 0.18));
    background-size: 200% 100%;
    animation: identity-loading 1.4s ease-in-out infinite;
  }

  .identity-row-skeleton.small {
    height: 38px;
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

  .identity-edit-close {
    width: 34px;
    height: 34px;
    border: 1px solid #d7e0ee;
    border-radius: 8px;
    background: #ffffff;
    color: #071638;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .identity-edit-summary,
  .identity-edit-card,
  .identity-edit-advanced {
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

  .identity-edit-advanced {
    width: 100%;
    min-height: 38px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 14px;
    color: #071638;
    font-size: 0.86rem;
    font-weight: 700;
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

  .identity-no-result {
    padding: 1rem;
    border-radius: 8px;
    border: 1px dashed rgba(148, 163, 184, 0.45);
    color: #64748b;
    background: rgba(248, 250, 252, 0.75);
    text-align: center;
    font-size: 0.9rem;
  }

  .identity-edit-drawer-footer {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
  }

  @keyframes identity-loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  @media (max-width: 1280px) {
    .identity-filter-card {
      grid-template-columns: 1fr;
    }

    .identity-status-tabs {
      justify-self: stretch;
    }

    .identity-main-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 920px) {
    :global(.identity-sources-page) {
      padding: 20px 16px 28px;
    }

    .identity-kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .identity-clean-table {
      min-width: 900px;
    }

    .identity-table-card {
      overflow-x: auto;
    }
  }

  @media (max-width: 640px) {
    .identity-kpi-grid {
      grid-template-columns: 1fr;
      gap: 12px;
    }

    .identity-page-actions,
    .identity-selects,
    .identity-detail-actions,
    .identity-table-footer {
      width: 100%;
      flex-direction: column;
      align-items: stretch;
    }

    .identity-status-tabs {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .identity-detail-list div {
      grid-template-columns: 1fr;
      gap: 4px;
    }
  }
</style>
