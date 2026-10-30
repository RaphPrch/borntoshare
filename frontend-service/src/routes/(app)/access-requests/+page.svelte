<script lang="ts">
  import type { PrincipalSearchItem } from '$lib/utils/principal-search';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { goto, invalidateAll } from '$app/navigation';
  import { page } from '$app/stores';
  import { normalizeMe } from '$lib/types/me';
  import { adoptAccessGroup, bulkDecision, getAccessRequestDetails, getApprovalPreview, type ApprovalPreview } from '$lib/api/access-requests';
  import ApprovalPlan from '$lib/components/access-requests/ApprovalPlan.svelte';
  import { listActivityByTarget, type ActivityEvent } from '$lib/api/activity';
  import { renderActivity } from '$lib/activity/formatter';
  import { onDestroy } from 'svelte';
  import NewAccessRequestModal from '$lib/components/access-requests/NewAccessRequestModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { initials, formatDateTime, formatDate, timeAgo } from '$lib/utils/format';
  import { getRequestStatusMeta, requestToneVariant } from '$lib/utils/access-request-status';
  import {
    mapAccessRequestDecisionError,
    mapAccessRequestDecisionErrorFromBulk
  } from '$lib/utils/request-decision-errors';
  import {
    accessRequestAccessLabel,
    accessRequestId,
    accessRequestRequesterName,
    accessRequestTargetLabel,
    accessRequestTargetPath
  } from '$lib/mappers/access-requests.mapper';

  type Segment = 'pending' | 'applied' | 'closed' | 'all';
  type AccessKind = 'read' | 'write' | 'other';

  export let data: {
    requests: any[];
    segment?: Segment;
    query?: string;
    me?: unknown;
    navigation?: { guardianRootIds?: number[] };
  };

  const DAY = 86_400_000;

  let segment: Segment = data.segment ?? 'pending';
  let searchText = data.query ?? '';
  let accessFilter: 'all' | AccessKind = 'all';
  let listPage = 1;
  let listPageSize = 10;

  let selectedRequestId: number | null = null;
  let selectedRequestDetail: any | null = null;
  let detailLoading = false;
  let detailError = '';
  let detailLoadToken = 0;
  let decisionComment = '';
  let decisionRunning: 'approve' | 'reject' | 'revoke' | null = null;
  let showRevokeConfirm = false;
  // Provisioning log of the open request (one entry per step, written by the server as it goes)
  let provisioningLog: ActivityEvent[] = [];
  // What the approval will do (reviewers), then what it did once applied
  let approvalPreview: ApprovalPreview | null = null;
  let appliedPreview: ApprovalPreview | null = null;
  let logTimer: ReturnType<typeof setInterval> | null = null;
  // Last failed decision: code, hint and, for a name conflict, the group an admin can adopt
  let decisionFailure: { code?: string | null; hint?: string | null; access_profile_id?: number | null; existing_dn?: string | null } | null = null;
  let adopting = false;
  let showCreateRequestModal = false;
  let createPrefillStorageRootId: number | null = null;
  let createPrefillAccessLevel: string | null = null;
  let createPrefillPrincipal: PrincipalSearchItem | null = null;
  let requestParamId: number | null = null;
  let lastAutoSelectedRequestId: number | null = null;

  const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase();
  const statusOf = (row: any): string => norm(row?.status ?? row?.workflow_status ?? row?.decision_status) || 'pending';
  const isPending = (row: any): boolean => ['pending', 'waiting', 'review'].some((key) => statusOf(row).includes(key));
  const isApplied = (row: any): boolean => ['executed', 'approved', 'enforced', 'applied'].includes(statusOf(row));
  const createdMs = (row: any): number => new Date(String(row?.created_at ?? row?.requested_at ?? '')).getTime() || 0;
  const expiresMs = (row: any): number => new Date(String(row?.expires_at ?? '')).getTime() || 0;

  function segmentOf(row: any): Exclude<Segment, 'all'> {
    if (isPending(row)) return 'pending';
    if (isApplied(row)) return 'applied';
    return 'closed';
  }

  function accessKind(row: any): AccessKind {
    const label = norm(accessRequestAccessLabel(row));
    if (label.includes('write') || label.includes('écriture') || label.includes('contrib')) return 'write';
    if (label.includes('read') || label.includes('lecture')) return 'read';
    return 'other';
  }

  const accessLabel = (row: any): string =>
    ({ read: t('Read'), write: t('Write'), other: accessRequestAccessLabel(row) })[accessKind(row)];

  function durationDays(row: any): number {
    const direct = Number(row?.ttl_days ?? row?.duration_days ?? 0);
    if (Number.isFinite(direct) && direct > 0) return Math.round(direct);
    const expires = expiresMs(row);
    return expires ? Math.max(1, Math.ceil((expires - (createdMs(row) || Date.now())) / DAY)) : 0;
  }

  const durationLabel = (row: any): string => {
    const days = durationDays(row);
    return days === 0 ? t('Permanent') : days === 1 ? t('1 day') : t('{count} days', { count: days });
  };

  const requesterName = (row: any): string => accessRequestRequesterName(row);
  const requesterDepartment = (row: any): string =>
    String(row?.requested_for_department ?? row?.requester_department ?? row?.department ?? row?.requested_principal_json?.department ?? '').trim();
  const resourceName = (row: any): string => accessRequestTargetLabel(row);
  const resourcePath = (row: any): string => {
    const path = String(row?.root_path ?? row?.target_path ?? row?.resource_path ?? accessRequestTargetPath(row) ?? '').trim();
    return path && path !== '—' ? path : '';
  };
  const requestCode = (row: any): string => String(row?.request_code ?? row?.code ?? `#${accessRequestId(row)}`);
  const justification = (row: any): string => String(row?.justification ?? row?.business_justification ?? row?.reason ?? '').trim();
  const statusMeta = (row: any) => {
    const meta = getRequestStatusMeta(statusOf(row));
    return isPending(row) ? { ...meta, label: t('Guardian review') } : meta;
  };
  const storageRootIdFromRow = (row: any): number | null => {
    const value = Number(row?.storage_root_id ?? row?.target_id ?? 0);
    return Number.isFinite(value) && value > 0 ? value : null;
  };

  $: requests = Array.isArray(data.requests) ? data.requests : [];
  $: me = normalizeMe(data.me);
  $: guardianRootIds = (data.navigation?.guardianRootIds ?? []).map(Number).filter((value) => value > 0);
  $: canReviewAny = me?.is_admin === true || guardianRootIds.length > 0;
  $: isReviewAllowed = (row: any): boolean =>
    me?.is_admin === true || (storageRootIdFromRow(row) !== null && guardianRootIds.includes(storageRootIdFromRow(row) as number));

  // Counters (computed on every request the user can see)
  $: now = Date.now();
  $: pendingRows = requests.filter(isPending);
  $: oldestPendingMs = pendingRows.reduce((min, row) => Math.min(min, createdMs(row) || now), now);
  $: appliedRows = requests.filter(isApplied);
  $: appliedRecent = appliedRows.filter((row) => now - createdMs(row) <= 30 * DAY).length;
  $: closedRows = requests.filter((row) => segmentOf(row) === 'closed');
  $: rejectedCount = closedRows.filter((row) => ['rejected', 'failed'].includes(statusOf(row))).length;
  $: expiringSoon = appliedRows.filter((row) => expiresMs(row) > now && expiresMs(row) - now <= 7 * DAY).length;
  $: segmentCounts = { pending: pendingRows.length, applied: appliedRows.length, closed: closedRows.length, all: requests.length };

  $: visibleRequests = requests
    .filter((row) => segment === 'all' || segmentOf(row) === segment)
    .filter((row) => accessFilter === 'all' || accessKind(row) === accessFilter)
    .filter((row) => {
      const q = norm(searchText);
      if (!q) return true;
      return [requesterName(row), requesterDepartment(row), resourceName(row), resourcePath(row), requestCode(row)].map(norm).join(' ').includes(q);
    })
    .sort((a, b) => createdMs(b) - createdMs(a));
  $: segment, accessFilter, searchText, (listPage = 1);
  $: pageRequests = visibleRequests.slice((listPage - 1) * listPageSize, listPage * listPageSize);

  $: selectedRequest = selectedRequestId
    ? selectedRequestDetail ?? requests.find((row) => accessRequestId(row) === selectedRequestId) ?? null
    : null;
  $: canReviewSelected = Boolean(selectedRequest) && isPending(selectedRequest) && isReviewAllowed(selectedRequest);
  $: canRevokeSelected =
    Boolean(selectedRequest) && isApplied(selectedRequest) && isReviewAllowed(selectedRequest) &&
    (!expiresMs(selectedRequest) || expiresMs(selectedRequest) > now);

  $: {
    const openCreate = norm($page.url.searchParams.get('create'));
    showCreateRequestModal = openCreate === '1' || openCreate === 'true';
    const prefillRootId = Number($page.url.searchParams.get('root') ?? 0);
    createPrefillStorageRootId = prefillRootId > 0 ? prefillRootId : null;
    createPrefillAccessLevel = String($page.url.searchParams.get('permission') ?? '').trim() || null;
    // ?principal_dn=…&principal_username=…&principal_name=…&principal_source=… (⌘K palette)
    const prefillDn = String($page.url.searchParams.get('principal_dn') ?? '').trim();
    createPrefillPrincipal = prefillDn
      ? {
          id: prefillDn,
          type: 'user',
          dn: prefillDn,
          username: $page.url.searchParams.get('principal_username'),
          display_name: $page.url.searchParams.get('principal_name'),
          identity_source_id: Number($page.url.searchParams.get('principal_source') ?? 0) || null,
          auth_source: 'ad'
        }
      : null;
    const targetRequestId = Number($page.url.searchParams.get('request') ?? 0);
    requestParamId = targetRequestId > 0 ? targetRequestId : null;
  }
  $: if (!requestParamId) lastAutoSelectedRequestId = null;
  $: if (requestParamId && requestParamId !== lastAutoSelectedRequestId) {
    lastAutoSelectedRequestId = requestParamId;
    const target = requests.find((row) => accessRequestId(row) === requestParamId);
    if (target) selectRequest(target);
    else openRequest(requestParamId);
  }

  const SEGMENTS: Segment[] = ['pending', 'applied', 'closed', 'all'];
  // Labels are translated when read
  const segmentLabel = (key: Segment): string =>
    ({ pending: t('To review'), applied: t('Applied'), closed: t('Closed'), all: t('All') })[key];

  function setUrl(update: (params: URLSearchParams) => void): void {
    const params = new URLSearchParams($page.url.searchParams);
    update(params);
    const qs = params.toString();
    goto(`/access-requests${qs ? `?${qs}` : ''}`, { replaceState: true, noScroll: true, keepFocus: true });
  }

  function selectSegment(key: Segment): void {
    segment = key;
    setUrl((params) => params.set('status', key));
  }

  function selectRequest(row: any): void {
    selectedRequestDetail = row;
    openRequest(accessRequestId(row));
  }

  function openRequest(id: number): void {
    selectedRequestId = id;
    detailError = '';
    decisionComment = '';
    decisionFailure = null;
    provisioningLog = [];
    approvalPreview = null;
    appliedPreview = null;
    void loadRequestDetail(id);
    void loadProvisioningLog(id);
    void loadApprovalPreview(id);
  }

  async function loadApprovalPreview(id: number): Promise<void> {
    try {
      const preview = await getApprovalPreview(fetch, id);
      if (selectedRequestId === id) approvalPreview = preview;
    } catch {
      // Only reviewers get it (403 otherwise); the request stays readable without it
    }
  }

  // created, reused, adopted… from the provisioning log of the approval
  $: groupOutcome =
    provisioningLog
      .map((event) => String(event.action ?? ''))
      .filter((action) => /^ad_group_(created|recreated|reused|adopted)$/.test(action))
      .map((action) => action.replace('ad_group_', ''))
      .pop() ?? null;

  async function loadProvisioningLog(id: number): Promise<void> {
    try {
      const rows = await listActivityByTarget(fetch, 'access_request', id, 100);
      if (selectedRequestId === id) provisioningLog = [...rows].reverse();
    } catch {
      // The log is a convenience: the request stays usable without it
    }
  }

  // Live progress while the server runs the steps (the approval call waits for AD)
  function followLog(id: number, on: boolean): void {
    if (logTimer) clearInterval(logTimer);
    logTimer = on ? setInterval(() => void loadProvisioningLog(id), 2000) : null;
  }

  onDestroy(() => followLog(0, false));

  async function loadRequestDetail(id: number): Promise<void> {
    const token = ++detailLoadToken;
    detailLoading = true;
    try {
      const detail = await getAccessRequestDetails(fetch, id);
      if (token === detailLoadToken && selectedRequestId === id) selectedRequestDetail = detail;
    } catch {
      if (token === detailLoadToken) detailError = t('The full details could not be loaded.');
    } finally {
      if (token === detailLoadToken) detailLoading = false;
    }
  }

  function closeDetail(): void {
    selectedRequestId = null;
    selectedRequestDetail = null;
    detailError = '';
    decisionFailure = null;
    provisioningLog = [];
    approvalPreview = null;
    appliedPreview = null;
    detailLoading = false;
    decisionComment = '';
    detailLoadToken += 1;
    if (requestParamId) setUrl((params) => params.delete('request'));
  }

  async function runDecision(decision: 'approve' | 'reject' | 'revoke'): Promise<void> {
    if (!selectedRequest || decisionRunning) return;
    const id = accessRequestId(selectedRequest);
    if (!id) return;
    decisionRunning = decision;
    detailError = '';
    decisionFailure = null;
    if (decision !== 'reject') followLog(id, true);
    try {
      const comment = decisionComment.trim();
      const result = await bulkDecision(fetch, [id], decision, comment || undefined);
      if (Number(result?.failed_ids?.length ?? 0) > 0) {
        decisionFailure = result?.failed_details?.[id] ?? null;
        const mapped = decision === 'approve'
          ? mapAccessRequestDecisionErrorFromBulk(result, { fallbackStorageRootId: storageRootIdFromRow(selectedRequest) })
          : mapAccessRequestDecisionError({
              detail: result?.failed_details?.[id] ?? null,
              reason: result?.failed_reasons?.[id] ?? null,
              fallbackStorageRootId: storageRootIdFromRow(selectedRequest)
            });
        detailError = mapped.message;
        decisionFailure = { ...(decisionFailure ?? {}), hint: mapped.hint };
        toast.error(mapped.message);
        return;
      }
      showRevokeConfirm = false;
      toast.success({ approve: t('Request approved.'), reject: t('Request rejected.'), revoke: t('Access revoked.') }[decision]);
      if (decision === 'approve' && approvalPreview) {
        // The drawer stays open on the result: group, member, ACL, and what the requester has to do
        appliedPreview = approvalPreview;
        await Promise.all([loadRequestDetail(id), loadProvisioningLog(id), invalidateAll()]);
        return;
      }
      closeDetail();
      await invalidateAll();
    } catch {
      toast.error({ approve: t('Approval failed.'), reject: t('Rejection failed.'), revoke: t('Revocation failed.') }[decision]);
    } finally {
      followLog(id, false);
      decisionRunning = null;
      if (selectedRequestId === id) void loadProvisioningLog(id);
    }
  }

  // Name conflict: a platform admin takes over the existing group, then the approval runs again
  async function adoptAndApprove(): Promise<void> {
    const profileId = Number(decisionFailure?.access_profile_id ?? 0);
    const groupDn = String(decisionFailure?.existing_dn ?? '');
    if (!profileId || !groupDn || adopting) return;
    adopting = true;
    try {
      await adoptAccessGroup(fetch, profileId, groupDn);
      await runDecision('approve');
    } catch {
      toast.error(t('The group could not be adopted.'));
    } finally {
      adopting = false;
    }
  }

  const LOG_ICONS: Record<string, string> = { success: 'bi-check-circle-fill', in_progress: 'bi-clock', failure: 'bi-x-octagon-fill' };
  const logState = (event: ActivityEvent): string => {
    const value = String(event?.result ?? event?.outcome ?? 'success').toLowerCase();
    return value in LOG_ICONS ? value : 'success';
  };

  function exportRequests(): void {
    downloadCsv(csvFilename('access-requests'), [
      { header: t('Code'), value: requestCode },
      { header: t('Requester'), value: requesterName },
      { header: t('Resource'), value: resourceName },
      { header: t('Path'), value: resourcePath },
      { header: t('Access'), value: accessLabel },
      { header: t('Duration (days)'), value: durationDays },
      { header: t('Status'), value: (row: any) => statusMeta(row).label },
      { header: t('Requested on'), value: (row: any) => formatDateTime(row?.created_at) }
    ], visibleRequests);
  }

  async function openCreateRequestModal(): Promise<void> {
    setUrl((params) => params.set('create', '1'));
  }

  async function closeCreateRequestModal(): Promise<void> {
    showCreateRequestModal = false;
    setUrl((params) => params.delete('create'));
  }

  async function handleAccessRequestCreated(): Promise<void> {
    await closeCreateRequestModal();
    await invalidateAll();
  }

  // Progress of the selected request: submitted -> guardian review -> applied -> ends
  $: progress = selectedRequest
    ? [
        { label: t('Submitted'), value: formatDateTime(selectedRequest.created_at), state: 'done' },
        isPending(selectedRequest)
          ? { label: t('Guardian review'), value: t('In progress'), state: 'current' }
          : { label: statusMeta(selectedRequest).label, value: formatDateTime(selectedRequest.decided_at ?? selectedRequest.updated_at), state: isApplied(selectedRequest) ? 'done' : 'stopped' },
        {
          label: t('Applied'),
          value: isApplied(selectedRequest) ? t('AD group membership') : '—',
          state: isApplied(selectedRequest) ? 'done' : 'waiting'
        },
        {
          label: t('Ends'),
          value: expiresMs(selectedRequest) ? formatDate(selectedRequest.expires_at) : durationLabel(selectedRequest),
          state: expiresMs(selectedRequest) && expiresMs(selectedRequest) < now ? 'done' : 'waiting'
        }
      ]
    : [];

  $: timeline = selectedRequest && Array.isArray(selectedRequest.timeline) ? selectedRequest.timeline : [];

  // Workflow event types -> readable labels (unknown types keep their own label)
  // (v_access_request_timeline: provision = execution queued or running, enforce = done, enforce_failed = failed)
  const EVENT_LABELS: Array<[string, string]> = [
    ['submit', 'Submitted'],
    ['approve', 'Approved'],
    ['reject', 'Rejected'],
    ['fail', 'AD group change failed'],
    ['provision', 'AD group change in progress'],
    ['enforce', 'AD group membership applied'],
    ['revoke', 'Revoked'],
    ['expire', 'Expired'],
    ['comment', 'Comment']
  ];
  function eventLabel(event: any): string {
    const type = norm(event?.event_type ?? event?.type ?? event?.action);
    const known = EVENT_LABELS.find(([key]) => type.includes(key));
    return known ? t(known[1]) : String(event?.label ?? event?.event_type ?? t('Event'));
  }
  const eventActor = (event: any): string =>
    String(event?.actor_display ?? event?.actor_name ?? event?.actor ?? '').trim();
</script>

<div class="ar-page">
  <header class="ar-head">
    <div class="ar-title">
      <h1>{t('Access requests')}</h1>
      <p>
        {t('{pending} to review · {applied} applied · {expiring} ending within 7 days', { pending: pendingRows.length, applied: appliedRows.length, expiring: expiringSoon })}{#if pendingRows.length > 0}{' · '}{t('Oldest: {age}', { age: timeAgo(new Date(oldestPendingMs).toISOString()) })}{/if}
      </p>
    </div>
    <label class="ar-search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" aria-label={t('Search access requests')} placeholder={t('Search requester, resource, path…')} bind:value={searchText} />
    </label>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={openCreateRequestModal}>
      <i class="bi bi-plus-lg" aria-hidden="true"></i>
      {t('New request')}
    </button>
  </header>

  <div class="ar-filters">
    <div class="ar-seg" role="tablist" aria-label={t('Request status')}>
      {#each SEGMENTS as key}
        <button type="button" role="tab" aria-selected={segment === key} class:on={segment === key} on:click={() => selectSegment(key)}>
          {segmentLabel(key)} <span>{segmentCounts[key]}</span>
        </button>
      {/each}
    </div>
    <div class="ar-chips" role="group" aria-label={t('Access')}>
      {#each [{ key: 'all', label: t('All access') }, { key: 'read', label: t('Read') }, { key: 'write', label: t('Write') }] as item}
        <button type="button" class:on={accessFilter === item.key} aria-pressed={accessFilter === item.key} on:click={() => (accessFilter = item.key as typeof accessFilter)}>{item.label}</button>
      {/each}
    </div>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm ar-export" on:click={exportRequests} disabled={visibleRequests.length === 0}>
      <i class="bi bi-download" aria-hidden="true"></i>
      {t('Export')}
    </button>
  </div>

  <div class="ar-body">
  <section class="ar-list">
    <div class="b2s-table-wrap">
      <table class="b2s-table ar-table">
        <thead>
          <tr>
            <th>{t('Requester')}</th>
            <th>{t('Resource')}</th>
            <th>{t('Access')}</th>
            {#if segment !== 'pending'}<th>{t('Status')}</th>{/if}
            <th>{segment === 'pending' ? t('Waiting') : t('Requested')}</th>
          </tr>
        </thead>
        <tbody>
          {#if pageRequests.length === 0}
            <tr>
              <td colspan="5" class="ar-empty">
                {segment === 'pending' ? t('No request is waiting for a review.') : t('No request matches these filters.')}
              </td>
            </tr>
          {:else}
            {#each pageRequests as request (accessRequestId(request))}
              {@const meta = statusMeta(request)}
              <tr
                class:selected={selectedRequestId === accessRequestId(request)}
                tabindex="0"
                on:click={() => selectRequest(request)}
                on:keydown={(event) => event.key === 'Enter' && selectRequest(request)}
              >
                <td>
                  <div class="ar-person">
                    <span class="ar-avatar">{initials(requesterName(request), '??')}</span>
                    <div>
                      <strong>{requesterName(request)}</strong>
                      {#if requesterDepartment(request)}<small>{requesterDepartment(request)}</small>{/if}
                    </div>
                  </div>
                </td>
                <td>
                  <strong>{resourceName(request)}</strong>
                  {#if resourcePath(request)}<small class="ar-mono">{resourcePath(request)}</small>{/if}
                </td>
                <td>
                  <StatusBadge compact showDot={false} variant={accessKind(request) === 'write' ? 'warning' : 'info'} label={accessLabel(request)} />
                </td>
                {#if segment !== 'pending'}
                  <td><StatusBadge compact variant={requestToneVariant(meta.tone)} label={meta.label} /></td>
                {/if}
                <td class="ar-nowrap" class:ar-late={isPending(request) && now - createdMs(request) > 3 * DAY} title={formatDateTime(request.created_at)}>
                  {timeAgo(request.created_at)}
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
    {#if visibleRequests.length > 0}
      <Pagination total={visibleRequests.length} bind:page={listPage} bind:pageSize={listPageSize} pageSizes={[10, 25, 50]} />
    {/if}
  </section>
<aside class="ar-side" aria-label={t('Decision')}>
  {#if selectedRequest}
    <div class="ar-side-head">
      <div class="ar-person">
        <span class="ar-avatar ar-avatar--lg">{initials(requesterName(selectedRequest), '??')}</span>
        <div>
          <strong>{requesterName(selectedRequest)}</strong>
          <small class="ar-mono">{requestCode(selectedRequest)}</small>
        </div>
      </div>
      <button type="button" class="ar-close" aria-label={t('Close')} on:click={closeDetail}><i class="bi bi-x-lg" aria-hidden="true"></i></button>
    </div>
    <p class="ar-sentence">
      {accessKind(selectedRequest) === 'write' ? t('requests write access to') : accessKind(selectedRequest) === 'read' ? t('requests read access to') : t('requests access to')}
      <strong>{resourceName(selectedRequest)}</strong>
    </p>
    <div class="ar-badges">
      <StatusBadge compact variant={requestToneVariant(statusMeta(selectedRequest).tone)} label={statusMeta(selectedRequest).label} />
      <StatusBadge compact showDot={false} variant={accessKind(selectedRequest) === 'write' ? 'warning' : 'info'} label={accessLabel(selectedRequest)} />
      <StatusBadge compact showDot={false} variant="muted" label={durationLabel(selectedRequest)} />
    </div>
  {/if}

  {#if selectedRequest}
    <div class="ar-detail">
      {#if detailLoading}<LoadingState>{t('Loading full details…')}</LoadingState>{/if}
      {#if detailError}
        <InlineAlert tone={decisionFailure?.code === 'AD_JOB_STILL_RUNNING' ? 'warning' : 'error'}>
          <strong>{detailError}</strong>
          {#if decisionFailure?.hint}<div>{decisionFailure.hint}</div>{/if}
          {#if decisionFailure?.code === 'AD_GROUP_NAME_CONFLICT' && decisionFailure?.existing_dn}
            <div class="ar-conflict">
              <span class="ar-mono">{decisionFailure.existing_dn}</span>
              {#if me?.is_admin === true && decisionFailure?.access_profile_id}
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={adopting || Boolean(decisionRunning)} on:click={adoptAndApprove}>
                  <i class="bi bi-link-45deg" aria-hidden="true"></i>
                  {adopting ? t('Adopting…') : t('Adopt this group and approve')}
                </button>
              {/if}
            </div>
          {/if}
        </InlineAlert>
      {/if}

      <ol class="ar-progress" aria-label={t('Request progress')}>
        {#each progress as step}
          <li class={`is-${step.state}`}>
            <span>{step.label}</span>
            <strong>{step.value}</strong>
          </li>
        {/each}
      </ol>

      <section>
        <h3>{t('Request')}</h3>
        <dl class="b2s-kv">
          <dt>{t('Resource')}</dt>
          <dd>{resourceName(selectedRequest)} {#if resourcePath(selectedRequest)}<span class="ar-mono">{resourcePath(selectedRequest)}</span>{/if}</dd>
          <dt>{t('Access')}</dt>
          <dd>
            {accessLabel(selectedRequest)}
            {#if selectedRequest.group_name || selectedRequest.expected_group_name}
              · <span class="ar-mono">{selectedRequest.group_name || selectedRequest.expected_group_name}</span>
            {/if}
          </dd>
          <dt>{t('Duration')}</dt>
          <dd>{durationLabel(selectedRequest)}{expiresMs(selectedRequest) ? ` · ${t('until {date}', { date: formatDate(selectedRequest.expires_at) })}` : ''}</dd>
          <dt>{t('Requested')}</dt>
          <dd>{formatDateTime(selectedRequest.created_at)}</dd>
        </dl>
      </section>

      <section>
        <h3>{t('Justification')}</h3>
        <blockquote class="ar-quote">{justification(selectedRequest) || t('No justification provided.')}</blockquote>
      </section>

      {#if appliedPreview}
        <section>
          <h3>{t('Access applied')}</h3>
          <ApprovalPlan preview={appliedPreview} done {groupOutcome} />
        </section>
      {:else if canReviewSelected && approvalPreview}
        <section>
          <h3>{t('What the approval does')}</h3>
          <ApprovalPlan preview={approvalPreview} />
        </section>
      {/if}

      {#if provisioningLog.length > 0 || decisionRunning === 'approve' || decisionRunning === 'revoke'}
        <section>
          <h3>{t('Provisioning log')}</h3>
          <ol class="ar-log" aria-live="polite">
            {#each provisioningLog as event (event.id ?? `${event.action}-${event.event_time}`)}
              {@const rendered = renderActivity(event)}
              <li class={`is-${logState(event)}`}>
                <i class={`bi ${LOG_ICONS[logState(event)]}`} aria-hidden="true"></i>
                <div>
                  <strong>{rendered.title}</strong>
                  {#if rendered.description}<span>{rendered.description}</span>{/if}
                </div>
                <small>{formatDateTime(event.event_time ?? event.created_at)}</small>
              </li>
            {/each}
            {#if decisionRunning === 'approve' || decisionRunning === 'revoke'}
              <li class="is-in_progress">
                <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
                <div><strong>{t('Waiting for Active Directory…')}</strong></div>
              </li>
            {/if}
          </ol>
        </section>
      {:else if timeline.length > 0}
        <section>
          <h3>{t('History')}</h3>
          <ul class="ar-history">
            {#each timeline as event}
              <li>
                <span>
                  <strong>{eventLabel(event)}</strong>
                  {#if eventActor(event)}<small>{t('by {name}', { name: eventActor(event) })}</small>{/if}
                </span>
                <small>{formatDateTime(event?.created_at)}</small>
              </li>
            {/each}
          </ul>
        </section>
      {/if}

      {#if canReviewSelected}
        <section>
          <label for="decision-comment" class="ar-label">{t('Comment (optional)')}</label>
          <textarea id="decision-comment" class="ar-textarea" bind:value={decisionComment} placeholder={t('Explain your decision to the requester…')}></textarea>
        </section>
      {/if}
    </div>
  {/if}

  {#if selectedRequest}
  <div class="ar-side-foot">
  <p class="ar-foot-note">
    {#if selectedRequest && canReviewSelected}
      {t('You can decide on this request.')}
    {:else if selectedRequest && isPending(selectedRequest)}
      {t('A guardian of this storage root or a platform administrator decides.')}
    {:else if canRevokeSelected}
      {t('Revoking removes the AD group membership now.')}
    {/if}
  </p>
  <div class="ar-foot-actions">
    {#if canReviewSelected}
      <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={Boolean(decisionRunning)} on:click={() => runDecision('reject')}>
        <i class="bi bi-x-lg" aria-hidden="true"></i>
        {decisionRunning === 'reject' ? t('Rejecting…') : t('Reject')}
      </button>
      <button
        type="button"
        class="b2s-btn b2s-btn-primary"
        disabled={Boolean(decisionRunning) || approvalPreview?.can_approve === false}
        title={approvalPreview?.can_approve === false ? t('Fix the configuration shown above first') : undefined}
        on:click={() => runDecision('approve')}
      >
        <i class="bi bi-check2" aria-hidden="true"></i>
        {decisionRunning === 'approve' ? t('Approving…') : t('Approve')}
      </button>
    {:else}
      {#if canRevokeSelected}
        <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={Boolean(decisionRunning)} on:click={() => (showRevokeConfirm = true)}>
          <i class="bi bi-person-x" aria-hidden="true"></i>
          {t('Revoke access')}
        </button>
      {/if}
    {/if}
  </div>
  </div>
  {:else}
    <div class="ar-side-empty">
      <i class="bi bi-inbox" aria-hidden="true"></i>
      <p>{t('Select a request to see what its approval does.')}</p>
    </div>
  {/if}
</aside>
  </div>
</div>

<ConfirmActionModal
  open={showRevokeConfirm}
  onClose={() => (showRevokeConfirm = false)}
  onConfirm={() => runDecision('revoke')}
  title={t('Revoke this access?')}
  subtitle={selectedRequest ? `${requesterName(selectedRequest)} → ${resourceName(selectedRequest)}` : null}
  impactItems={[t('The AD group membership is removed.'), t('The requester must submit a new request to get access back.')]}
  confirmLabel={t('Revoke access')}
  confirmBusyLabel={t('Revoking…')}
  busy={decisionRunning === 'revoke'}
/>

<NewAccessRequestModal
  open={showCreateRequestModal}
  prefillStorageRootId={createPrefillStorageRootId}
  prefillAccessLevel={createPrefillAccessLevel}
  prefillPrincipal={createPrefillPrincipal}
  onClose={closeCreateRequestModal}
  onCreated={handleAccessRequestCreated}
/>

<style>
  .ar-page {
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: var(--b2s-page-padding);
  }

  .ar-head {
    display: flex;
    align-items: flex-end;
    gap: 12px;
  }

  .ar-title {
    flex: 1 1 320px;
    min-width: 0;
  }

  .ar-title h1 {
    margin: 0;
    font-size: 38px;
    line-height: 1.05;
    font-weight: 600;
    letter-spacing: -.03em;
  }

  .ar-title p {
    margin: 6px 0 0;
    color: var(--b2s-color-text-muted);
    font-size: 15px;
  }

  .ar-search {
    flex: 0 1 340px;
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 44px;
    margin: 0;
    padding: 0 14px;
    border-radius: 12px;
    background: var(--b2s-color-surface);
    border: 1px solid var(--b2s-color-border-strong);
    color: var(--b2s-color-text-muted);
  }

  .ar-search:focus-within {
    border-color: var(--b2s-color-text);
  }

  .ar-search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--b2s-color-text);
    font: inherit;
  }

  .ar-filters {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .ar-seg {
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    border-radius: 12px;
    background: var(--b2s-color-neutral-soft);
  }

  .ar-seg button {
    min-height: 38px;
    padding: 0 14px;
    border: 0;
    border-radius: 9px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
  }

  .ar-seg button.on {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    box-shadow: 0 1px 2px rgba(14, 18, 24, .12);
  }

  .ar-seg span {
    font-size: 12px;
    color: var(--b2s-color-text-muted);
  }

  .ar-chips {
    display: flex;
    gap: 8px;
  }

  .ar-chips button {
    min-height: 36px;
    padding: 0 13px;
    border-radius: 999px;
    border: 1px solid var(--b2s-color-border-strong);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text-muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
  }

  .ar-chips button.on {
    background: var(--b2s-color-text);
    border-color: var(--b2s-color-text);
    color: #fff;
    font-weight: 600;
  }

  .ar-export {
    margin-left: auto;
  }

  .ar-body {
    display: flex;
    align-items: flex-start;
    gap: 18px;
  }

  .ar-list,
  .ar-side {
    background: var(--b2s-color-surface);
    border: 1px solid var(--b2s-color-border);
    border-radius: 18px;
    box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06);
  }

  .ar-list {
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }

  .ar-side {
    flex: 0 0 420px;
    position: sticky;
    top: 16px;
    /* Below the page head: the decision buttons stay on screen without scrolling the page */
    max-height: calc(100vh - 190px);
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .ar-side-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .ar-side-head strong {
    font-size: 18px;
    font-weight: 600;
  }

  .ar-close {
    width: 32px;
    height: 32px;
    flex: none;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    cursor: pointer;
  }

  .ar-close:hover {
    background: var(--b2s-color-neutral-soft);
  }

  .ar-sentence {
    margin: 0;
    font-size: 20px;
    line-height: 1.3;
    letter-spacing: -.01em;
  }

  .ar-sentence strong {
    font-weight: 600;
  }

  .ar-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .ar-side-foot {
    position: sticky;
    bottom: -20px;
    margin: 0 -20px -20px;
    padding: 12px 20px 16px;
    background: var(--b2s-color-surface);
    border-top: 1px solid var(--b2s-color-border);
  }

  .ar-foot-note {
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--b2s-color-text-muted);
  }

  .ar-foot-note:empty {
    display: none;
  }

  .ar-foot-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .ar-foot-actions:empty {
    display: none;
  }

  .ar-side-empty {
    display: grid;
    justify-items: center;
    gap: 10px;
    padding: 56px 24px;
    text-align: center;
    color: var(--b2s-color-text-muted);
  }

  .ar-side-empty i {
    font-size: 26px;
  }

  .ar-side-empty p {
    margin: 0;
  }

  .ar-late {
    color: var(--b2s-color-danger);
    font-weight: 600;
  }

  .ar-avatar--lg {
    width: 48px;
    height: 48px;
    font-size: 15px;
  }

  .ar-table tbody tr {
    cursor: pointer;
  }

  .ar-table td small {
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .ar-table td strong {
    font-weight: 500;
  }

  .ar-mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
    overflow-wrap: anywhere;
  }

  .ar-nowrap {
    white-space: nowrap;
  }

  .ar-empty {
    padding: 32px 16px;
    color: var(--b2s-color-text-muted);
    text-align: center;
    cursor: default;
  }

  .ar-person {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .ar-person small {
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .ar-avatar {
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
    font-size: 11px;
    font-weight: 600;
  }

  .ar-detail {
    display: grid;
    gap: 22px;
  }

  .ar-detail h3 {
    margin: 0 0 10px;
    font-size: var(--b2s-fs-lg);
    font-weight: 600;
  }

  .ar-progress {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0;
    padding: 0;
    list-style: none;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    overflow: hidden;
  }

  .ar-progress li {
    display: grid;
    gap: 2px;
    padding: 12px 14px;
    font-size: var(--b2s-fs-xs);
  }

  .ar-progress li:nth-child(even) {
    border-left: 1px solid var(--b2s-color-border-soft);
  }

  .ar-progress li:nth-child(n + 3) {
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .ar-progress span {
    color: var(--b2s-color-text-muted);
  }

  .ar-progress strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .ar-progress li.is-current {
    background: var(--b2s-color-warning-soft);
  }

  .ar-progress li.is-current span {
    color: var(--b2s-color-warning-strong);
  }

  .ar-progress li.is-stopped {
    background: var(--b2s-color-danger-soft);
  }

  .ar-progress li.is-waiting strong {
    color: var(--b2s-color-text-faint);
  }

  .ar-quote {
    margin: 0;
    padding: 12px 14px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    font-size: var(--b2s-fs-sm);
  }

  .ar-history {
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--b2s-fs-sm);
  }

  .ar-history li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .ar-history strong {
    font-weight: 500;
  }

  .ar-history span small {
    margin-left: 6px;
  }

  .ar-history small {
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
  }

  .ar-log {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--b2s-fs-sm);
  }

  .ar-log li {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: start;
    padding: 8px 10px;
    border-radius: var(--b2s-radius-sm);
  }

  .ar-log li > i,
  .ar-log li > .spinner-border {
    margin-top: 2px;
  }

  .ar-log li.is-success > i { color: var(--b2s-color-success); }
  .ar-log li.is-in_progress > i { color: var(--b2s-color-info); }
  .ar-log li.is-failure { background: var(--b2s-color-danger-soft); }
  .ar-log li.is-failure > i { color: var(--b2s-color-danger); }

  .ar-log strong {
    display: block;
    font-weight: 500;
  }

  .ar-log span {
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .ar-log small {
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
  }

  .ar-conflict {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
    margin-top: 8px;
  }

  .ar-label {
    display: block;
    margin-bottom: 6px;
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .ar-textarea {
    width: 100%;
    min-height: 84px;
    padding: 10px 12px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    font: inherit;
    font-size: var(--b2s-fs-sm);
    resize: vertical;
  }
</style>
