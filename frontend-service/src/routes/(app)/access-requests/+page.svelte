<script lang="ts">
  import { copyText } from '$lib/utils/clipboard';
  import SavedViews from '$lib/components/ui/SavedViews.svelte';
  import ColumnPicker from '$lib/components/ui/ColumnPicker.svelte';
  import { resizableColumns } from '$lib/utils/resizable-columns';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { recall, remember } from '$lib/utils/remember';
  import { pulseOnIncrease } from '$lib/utils/motion';
  import QuotaRequestsStrip from '$lib/components/storage-roots/QuotaRequestsStrip.svelte';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { extendAccess } from '$lib/api/storage-root-permissions';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { t } from '$lib/i18n';
  import { goto, invalidateAll } from '$app/navigation';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { normalizeMe } from '$lib/types/me';
  import { cancelAccessRequest, adoptAccessGroup, bulkDecision, changeRequestPermission, getAccessRequestDetails, getApprovalPreview, type ApprovalPreview } from '$lib/api/access-requests';
  import ApprovalPlan from '$lib/components/access-requests/ApprovalPlan.svelte';
  import { listActivityByTarget, type ActivityEvent } from '$lib/api/activity';
  import { renderActivity } from '$lib/activity/formatter';
  import { onDestroy } from 'svelte';
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
    accessRequestTargetLabel
  } from '$lib/mappers/access-requests.mapper';
  import { reportUiError } from '$lib/errors';

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
  let accessFilter = recall('requests', { accessFilter: 'all' }).accessFilter as 'all' | AccessKind;
  $: remember('requests', { accessFilter });
  // Optional columns, kept in this browser; saved views of the filters
  let hiddenCols = (recall('requests-columns', { hidden: [] as unknown[] }).hidden as string[]).filter((k) => typeof k === 'string');
  $: remember('requests-columns', { hidden: hiddenCols });
  $: OPTIONAL_COLS = [
    { key: 'path', label: t('Path of the folder') },
    { key: 'level', label: t('Level') },
    { key: 'end', label: t('End') },
    { key: 'decision', label: t('Decision') }
  ];
  $: show = (key: string) => !hiddenCols.includes(key);
  function applyView(state: Record<string, unknown>) {
    accessFilter = (state.accessFilter as typeof accessFilter) ?? 'all';
    searchText = String(state.searchText ?? '');
    extra = (state.extra as typeof extra) ?? 'none';
    const wanted = (state.segment as Segment) ?? 'pending';
    if (wanted !== segment) selectSegment(wanted);
  }
  const PAGE = 50;
  let shown = PAGE;
  // Two more views of the counters: accesses ending within 30 days, requests refused in the last 30 days
  let extra: 'none' | 'ending' | 'refused' = 'none';

  let selectedRequestId: number | null = null;
  let selectedRequestDetail: any | null = null;
  let detailLoading = false;
  let detailError = '';
  let detailLoadToken = 0;
  let decisionComment = '';
  let decisionRunning: 'approve' | 'reject' | 'revoke' | null = null;
  let showRevokeConfirm = false;
  let showCancelConfirm = false;
  let cancelling = false;
  async function cancelSelected() {
    showCancelConfirm = false;
    const id = selectedRequest ? accessRequestId(selectedRequest) : 0;
    if (!id) return;
    cancelling = true;
    try {
      await cancelAccessRequest(fetch, Number(id));
      toast.success(t('Request cancelled.'));
      await invalidateAll();
      selectedRequestDetail = null;
    } catch (error) {
      reportUiError(error, t('Unable to cancel this request.'), 'access-requests.cancel');
    } finally {
      cancelling = false;
    }
  }
  // Provisioning log of the open request (one entry per step, written by the server as it goes)
  let provisioningLog: ActivityEvent[] = [];
  // What the approval will do (reviewers), then what it did once applied
  let approvalPreview: ApprovalPreview | null = null;
  let appliedPreview: ApprovalPreview | null = null;
  let logTimer: ReturnType<typeof setInterval> | null = null;
  // Last failed decision: code, hint and, for a name conflict, the group an admin can adopt
  let decisionFailure: { code?: string | null; hint?: string | null; access_profile_id?: number | null; existing_dn?: string | null } | null = null;
  let adopting = false;
  let levelEditing = false;
  let levelReason = '';
  let levelSaving = false;
  let checkedIds = new Set<number>();
  let bulkDecisionAsked: 'approve' | 'reject' | null = null;
  let bulkRunning = false;
  let bulkDone = 0;
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
    // A folder path only: never the technical id of a deleted folder (/storage_root/12)
    const path = String(row?.root_path ?? row?.target_path ?? row?.resource_path ?? '').trim();
    return path && path !== '—' && !path.startsWith('/storage_root') ? path : '';
  };
  const requestCode = (row: any): string => String(row?.request_code ?? row?.code ?? `#${accessRequestId(row)}`);
  const justification = (row: any): string => String(row?.justification ?? row?.business_justification ?? row?.reason ?? '').trim();
  // The guardian's comment on a decided request (older requests may repeat the justification there)
  const guardianComment = (row: any): string => {
    const comment = String(row?.decision_comment ?? '').trim();
    return statusOf(row) !== 'pending' && comment !== justification(row) ? comment : '';
  };
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
  $: appliedRows = requests.filter(isApplied);

  const decidedMs = (row: any): number => new Date(String(row?.decided_at ?? row?.revoked_at ?? row?.updated_at ?? '')).getTime() || 0;
  const endingSoon = (row: any): boolean => isApplied(row) && expiresMs(row) > now && expiresMs(row) - now <= 30 * DAY;
  const refusedRecently = (row: any): boolean => statusOf(row) === 'rejected' && now - decidedMs(row) <= 30 * DAY;
  $: counters = [
    { key: 'pending', label: t('To review'), count: pendingRows.length, tone: pendingRows.length ? 'warn' : '' },
    { key: 'applied', label: t('In force'), count: appliedRows.length, tone: '' },
    { key: 'ending', label: t('Ending within 30 days'), count: requests.filter(endingSoon).length, tone: '' },
    { key: 'refused', label: t('Refused · 30 d'), count: requests.filter(refusedRecently).length, tone: '' },
    { key: 'all', label: t('All'), count: requests.length, tone: '' }
  ];
  $: activeCounter = extra !== 'none' ? extra : segment === 'closed' ? 'all' : segment;
  function pickCounter(key: string): void {
    if (key === 'ending') { extra = 'ending'; selectSegment('applied'); }
    else if (key === 'refused') { extra = 'refused'; selectSegment('closed'); }
    else { extra = 'none'; selectSegment(key as Segment); }
  }

  $: visibleRequests = requests
    .filter((row) => segment === 'all' || segmentOf(row) === segment)
    .filter((row) => extra === 'none' || (extra === 'ending' ? endingSoon(row) : refusedRecently(row)))
    .filter((row) => accessFilter === 'all' || accessKind(row) === accessFilter)
    .filter((row) => {
      const q = norm(searchText);
      if (!q) return true;
      return [requesterName(row), requesterDepartment(row), resourceName(row), resourcePath(row), requestCode(row)].map(norm).join(' ').includes(q);
    })
    .sort((a, b) => createdMs(b) - createdMs(a));
  $: segment, extra, accessFilter, searchText, (shown = PAGE);
  $: pageRequests = visibleRequests.slice(0, shown);

  $: selectedRequest = selectedRequestId
    ? selectedRequestDetail ?? requests.find((row) => accessRequestId(row) === selectedRequestId) ?? null
    : null;
  $: canReviewSelected = Boolean(selectedRequest) && isPending(selectedRequest) && isReviewAllowed(selectedRequest);
  // A guardian does not decide on their own request; an administrator does (and it is traced)
  $: ownRequestBlocked = Boolean(selectedRequest?.own_request) && me?.is_admin !== true;
  $: canChangeLevel = Boolean(selectedRequest?.can_change_permission) && isPending(selectedRequest);
  $: originalLevel = String(selectedRequest?.original_permission ?? '').trim().toLowerCase();
  $: canRevokeSelected =
    Boolean(selectedRequest) && isApplied(selectedRequest) && isReviewAllowed(selectedRequest) &&
    (!expiresMs(selectedRequest) || expiresMs(selectedRequest) > now);

  $: {
    // Former links (?create=1&root=…&principal_dn=…) open the creation page with the same parameters
    if (browser && ['1', 'true'].includes(norm($page.url.searchParams.get('create')))) {
      const params = new URLSearchParams($page.url.searchParams);
      params.delete('create');
      void goto(`/access-requests/new${params.toString() ? `?${params}` : ''}`, { replaceState: true });
    }
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

  $: checkable = (row: any): boolean => isPending(row) && isReviewAllowed(row);
  $: pageCheckable = pageRequests.filter(checkable);
  $: allPageChecked = pageCheckable.length > 0 && pageCheckable.every((row) => checkedIds.has(accessRequestId(row)));
  // A selection never outlives its rows (decided elsewhere, filtered by the API)
  $: if (requests) {
    const live = new Set(requests.filter(isPending).map(accessRequestId));
    if ([...checkedIds].some((id) => !live.has(id))) checkedIds = new Set([...checkedIds].filter((id) => live.has(id)));
  }

  function toggleChecked(id: number): void {
    if (checkedIds.has(id)) checkedIds.delete(id);
    else checkedIds.add(id);
    checkedIds = checkedIds;
  }

  function togglePage(): void {
    const next = !allPageChecked;
    for (const row of pageCheckable) {
      if (next) checkedIds.add(accessRequestId(row));
      else checkedIds.delete(accessRequestId(row));
    }
    checkedIds = checkedIds;
  }

  // One at a time: each approval can wait for Active Directory, and the progress stays visible
  async function runBulkDecision(): Promise<void> {
    if (!bulkDecisionAsked) return;
    bulkRunning = true;
    const ids = [...checkedIds];
    const failed: number[] = [];
    let stoppedAt = -1;
    try {
      for (const [index, id] of ids.entries()) {
        bulkDone = index;
        let result: Awaited<ReturnType<typeof bulkDecision>> | null = null;
        try {
          result = await bulkDecision(fetch, [id], bulkDecisionAsked);
        } catch (e: unknown) {
          // Refused for this request only (their own request): the next ones can go on
          if ((e as { status?: number })?.status !== 403) throw e;
          failed.push(id);
          continue;
        }
        if (Number(result?.failed_ids?.length ?? 0) > 0) {
          failed.push(id);
          // Active Directory does not answer: the next ones would each wait as long
          if (result?.failed_details?.[id]?.code === 'AD_JOB_STILL_RUNNING') {
            stoppedAt = index;
            break;
          }
        }
      }
      const untouched = stoppedAt >= 0 ? ids.slice(stoppedAt + 1) : [];
      const done = ids.length - failed.length - untouched.length;
      if (stoppedAt >= 0) toast.error(t('Active Directory does not answer: {done} done, {left} left to process.', { done, left: failed.length + untouched.length }));
      else if (failed.length > 0) toast.error(t('{ok} done, {failed} failed: open each failed request to see why.', { ok: done, failed: failed.length }));
      else toast.success(t('{count} requests processed.', { count: ids.length }));
      checkedIds = new Set([...failed, ...untouched]);
      await invalidateAll();
    } catch {
      toast.error(bulkDecisionAsked === 'approve' ? t('Approval failed.') : t('Rejection failed.'));
      await invalidateAll();
    } finally {
      bulkRunning = false;
      bulkDone = 0;
      bulkDecisionAsked = null;
    }
  }

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

  // Guardians move the end of an access in force
  let extending = false;
  async function extendSelected(): Promise<void> {
    const id = selectedRequest ? accessRequestId(selectedRequest) : 0;
    if (!id || extending) return;
    extending = true;
    try {
      const result = await extendAccess(fetch, Number(id), 30);
      toast.success(t('Access extended until {date}.', { date: formatDate(result.expires_at ?? '') }));
      await invalidateAll();
      selectedRequestDetail = null;
    } catch (error) {
      reportUiError(error, t('Unable to extend this access.'), 'access-requests.extend');
    } finally {
      extending = false;
    }
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
    levelEditing = false;
    levelReason = '';
    detailLoadToken += 1;
    if (requestParamId) setUrl((params) => params.delete('request'));
  }

  async function changeLevel(): Promise<void> {
    if (!selectedRequest || levelSaving || !levelReason.trim()) return;
    const id = accessRequestId(selectedRequest);
    if (!id) return;
    const target = accessKind(selectedRequest) === 'write' ? 'read' : 'write';
    levelSaving = true;
    try {
      await changeRequestPermission(fetch, id, target, levelReason.trim());
      toast.success(target === 'read' ? t('The request now asks for read access.') : t('The request now asks for write access.'));
      levelEditing = false;
      levelReason = '';
      await invalidateAll();
      void loadApprovalPreview(id);
      void loadRequestDetail(id);
    } catch (e: unknown) {
      reportUiError(e, t('Unable to change the access level.'), 'access-request.permission');
    } finally {
      levelSaving = false;
    }
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

  // ---- Right click and quick decisions: the decision leaves after QUICK_DELAY, « Undo » until then ----------------
  const QUICK_DELAY = 5000;
  let menu: { row: any; at: { x: number; y: number } } | null = null;
  let quick = new Map<number, { decision: 'approve' | 'reject'; timer: ReturnType<typeof setTimeout> }>();
  let justDone = new Set<number>();

  function openMenu(row: any, event: MouseEvent): void {
    event.preventDefault();
    menu = { row, at: menuPositionFor(event) };
  }

  function menuItems(row: any): ContextMenuItem[] {
    const can = checkable(row);
    const own = Boolean(row?.own_request) && me?.is_admin !== true;
    const why = !isPending(row) ? t('Already decided') : own ? t('This is your own request: another guardian or an administrator approves it.') : !can ? t('You do not decide on this folder') : undefined;
    const rootId = storageRootIdFromRow(row);
    return [
      { key: 'approve', label: t('Approve') + ' (V)', icon: 'bi-check2-circle', disabled: !can || own, hint: why },
      { key: 'reject', label: t('Reject') + ' (R)', icon: 'bi-x-circle', disabled: !can || own, hint: why },
      { key: 'open', label: t('See the request'), icon: 'bi-layout-sidebar-reverse', separated: true },
      { key: 'folder', label: t('Open the folder'), icon: 'bi-folder2-open', disabled: !rootId },
      { key: 'copy', label: t('Copy the reference'), icon: 'bi-clipboard' }
    ];
  }

  function pickMenu(key: string): void {
    const row = menu?.row;
    if (!row) return;
    if (key === 'approve' || key === 'reject') quickDecide(row, key);
    else if (key === 'open') selectRequest(row);
    else if (key === 'folder') void goto(`/storage-roots?selected=${storageRootIdFromRow(row)}`);
    else if (key === 'copy') void copyText(requestCode(row)).then((ok) => ok && toast.success(t('Reference copied.')));
  }

  function quickDecide(row: any, decision: 'approve' | 'reject'): void {
    const id = accessRequestId(row);
    if (!id || quick.has(id) || !checkable(row) || (row?.own_request && me?.is_admin !== true)) return;
    const name = requesterName(row);
    const timer = setTimeout(() => void sendQuick(row, id, decision), QUICK_DELAY);
    quick.set(id, { decision, timer });
    quick = quick;
    toast.info(decision === 'approve' ? t('Approval of {name}: sent in 5 s.', { name }) : t('Rejection of {name}: sent in 5 s.', { name }), {
      duration: QUICK_DELAY,
      action: { label: t('Undo'), run: () => undoQuick(id) }
    });
  }

  function undoQuick(id: number): void {
    const pending = quick.get(id);
    if (!pending) return;
    clearTimeout(pending.timer);
    quick.delete(id);
    quick = quick;
    toast.info(t('Decision cancelled: nothing was sent.'));
  }

  async function sendQuick(row: any, id: number, decision: 'approve' | 'reject'): Promise<void> {
    try {
      const result = await bulkDecision(fetch, [id], decision);
      if (Number(result?.failed_ids?.length ?? 0) > 0) {
        const mapped = decision === 'approve'
          ? mapAccessRequestDecisionErrorFromBulk(result, { fallbackStorageRootId: storageRootIdFromRow(row) })
          : mapAccessRequestDecisionError({ detail: result?.failed_details?.[id] ?? null, reason: result?.failed_reasons?.[id] ?? null,
                                            fallbackStorageRootId: storageRootIdFromRow(row) });
        toast.error(mapped.message);
        selectRequest(row);
        return;
      }
      toast.success(decision === 'approve' ? t('Request approved.') : t('Request rejected.'));
      justDone.add(id);
      justDone = justDone;
      setTimeout(() => { justDone.delete(id); justDone = justDone; }, 4000);
      await invalidateAll();
    } catch (error: unknown) {
      reportUiError(error, decision === 'approve' ? t('Approval failed.') : t('Rejection failed.'), 'access-requests.quick-decision');
    } finally {
      quick.delete(id);
      quick = quick;
    }
  }

  function rowKeydown(event: KeyboardEvent, row: any): void {
    if (event.key === 'Enter') selectRequest(row);
    else if (event.key === 'v' || event.key === 'V') quickDecide(row, 'approve');
    else if (event.key === 'r' || event.key === 'R') quickDecide(row, 'reject');
    else if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault();
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      menu = { row, at: { x: rect.left + 24, y: rect.bottom } };
    }
  }

  onDestroy(() => { for (const pending of quick.values()) clearTimeout(pending.timer); });

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
  <header class="sg-head">
    <div class="sg-title">
      <h1>{t('Access requests')}</h1>
    </div>
    <label class="sg-search" style="flex-basis:340px">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" aria-label={t('Search access requests')} placeholder={t('Search requester, resource, path…')} bind:value={searchText} />
    </label>
    <a class="b2s-btn b2s-btn-primary" href="/access-requests/new">
      <i class="bi bi-plus-lg" aria-hidden="true"></i>
      {t('New request')}
    </a>
  </header>

  <QuotaRequestsStrip isAdmin={me?.is_admin === true} />

  <div class="ar-counters" role="group" aria-label={t('Request status')}>
    {#each counters as counter (counter.key)}
      <button type="button" class:on={activeCounter === counter.key} aria-pressed={activeCounter === counter.key} on:click={() => pickCounter(counter.key)}>
        <span>{counter.label}</span><b class:warn={counter.tone === 'warn'} use:pulseOnIncrease={counter.count}>{counter.count}</b>
      </button>
    {/each}
  </div>

  <div class="ar-filters">
    <div class="sg-seg" role="group" aria-label={t('Access')}>
      {#each [{ key: 'all', label: t('All levels') }, { key: 'read', label: t('Read') }, { key: 'write', label: t('Modify') }] as item}
        <button type="button" class:on={accessFilter === item.key} aria-pressed={accessFilter === item.key} on:click={() => (accessFilter = item.key as typeof accessFilter)}>{item.label}</button>
      {/each}
    </div>
    <SavedViews key="requests" current={{ segment, extra, accessFilter, searchText }} apply={applyView} />
    <span class="ar-filters__end">
      <ColumnPicker columns={OPTIONAL_COLS} hidden={hiddenCols} onChange={(next) => (hiddenCols = next)} />
    </span>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm ar-export" on:click={exportRequests} disabled={visibleRequests.length === 0}>
      <i class="bi bi-download" aria-hidden="true"></i>
      {t('Export')}
    </button>
  </div>

  {#if checkedIds.size > 0}
    <div class="ar-bulk" role="status">
      <strong>{t('{count} selected', { count: checkedIds.size })}</strong>
      <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" on:click={() => (bulkDecisionAsked = 'approve')}>{t('Approve all')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (bulkDecisionAsked = 'reject')}>{t('Reject all')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => (checkedIds = new Set())}>{t('Clear the selection')}</button>
    </div>
  {/if}

  <div class="ar-body">
  <section class="b2s-panel ar-list">
    <div class="b2s-table-wrap">
      <table class="b2s-table ar-table" use:resizableColumns={'requests'}>
        <thead>
          <tr>
            <th class="ar-check">
              {#if pageCheckable.length > 0}
                <input type="checkbox" aria-label={t('Select all')} checked={allPageChecked} on:change={togglePage} />
              {/if}
            </th>
            <th>{t('Requester')}</th>
            <th>{t('Folder')}</th>
            {#if show('level')}<th>{t('Level')}</th>{/if}
            <th>{t('Status')}</th>
            {#if !selectedRequest}{#if show('end')}<th>{t('End')}</th>{/if}{#if show('decision')}<th>{t('Decision')}</th>{/if}{/if}
          </tr>
        </thead>
        <tbody>
          {#if pageRequests.length === 0}
            <tr>
              <td colspan="7" class="ar-empty">
                {#if accessFilter !== 'all' || searchText || extra !== 'none'}
                  <EmptyStateInline message={t('No request matches these filters.')} actionLabel={t('Clear the filters')} actionIcon="bi-x-circle"
                    onAction={() => { accessFilter = 'all'; searchText = ''; extra = 'none'; }} />
                {:else}
                  <EmptyStateInline message={segment === 'pending' ? t('No request is waiting for a review.') : t('No request matches these filters.')}
                    actionLabel={t('New access request')} href="/access-requests/new" actionIcon="bi-plus-lg" shortcut="N" />
                {/if}
              </td>
            </tr>
          {:else}
            {#each pageRequests as request (accessRequestId(request))}
              {@const meta = statusMeta(request)}
              <tr
                class:selected={selectedRequestId === accessRequestId(request)}
                class:is-quick={quick.has(accessRequestId(request))}
                class:is-done={justDone.has(accessRequestId(request))}
                tabindex="0"
                on:click={() => selectRequest(request)}
                on:contextmenu={(event) => openMenu(request, event)}
                on:keydown={(event) => rowKeydown(event, request)}
              >
                <td class="ar-check" on:click|stopPropagation on:keydown|stopPropagation>
                  {#if checkable(request)}
                    <input
                      type="checkbox"
                      aria-label={t('Select {name}', { name: requesterName(request) })}
                      checked={checkedIds.has(accessRequestId(request))}
                      on:change={() => toggleChecked(accessRequestId(request))}
                    />
                  {/if}
                </td>
                <td>
                  <div class="ar-person">
                    <span class="ar-avatar">{initials(requesterName(request), '??')}</span>
                    <div>
                      <strong>{requesterName(request)}</strong>
                      <small class:ar-late={isPending(request) && now - createdMs(request) > 3 * DAY} title={formatDateTime(request.created_at)}>{requestCode(request)} · {timeAgo(request.created_at)}</small>
                    </div>
                  </div>
                </td>
                <td>
                  <strong>{resourceName(request)}</strong>
                  {#if show('path') && resourcePath(request)}<small class="ar-mono">{resourcePath(request)}</small>{/if}
                </td>
                {#if show('level')}
                <td>
                  <StatusBadge compact showDot={false} variant={accessKind(request) === 'write' ? 'warning' : 'info'} label={accessLabel(request)} />
                </td>
                {/if}
                <td>
                  {#if quick.has(accessRequestId(request))}
                    <span class="ar-quick">{quick.get(accessRequestId(request))?.decision === 'approve' ? t('Approved · sent in 5 s') : t('Rejected · sent in 5 s')}<span class="ar-quick__bar" aria-hidden="true"></span></span>
                  {:else if justDone.has(accessRequestId(request))}
                    <span class="ar-done"><i class="bi bi-check2" aria-hidden="true"></i>{t('Done')}</span>
                  {:else}
                    <StatusBadge compact variant={requestToneVariant(meta.tone)} label={meta.label} />
                  {/if}
                </td>
                {#if !selectedRequest}
                  {#if show('end')}
                  <td class="ar-end">
                    {#if isApplied(request) && expiresMs(request)}
                      {@const left = Math.max(0, Math.ceil((expiresMs(request) - now) / DAY))}
                      <small class:ar-late={left <= 7}>{t('in {days} d', { days: left })}</small>
                      <span class="ar-bar" aria-hidden="true"><span class:soon={left <= 7} style={`width:${Math.min(100, Math.round((left / Math.max(1, durationDays(request))) * 100))}%`}></span></span>
                    {:else if isApplied(request)}<small>{t('Permanent')}</small>{:else}<small class="ar-dim">—</small>{/if}
                  </td>
                  {/if}
                  {#if show('decision')}
                  <td class="ar-nowrap"><small class="ar-dim">{decidedMs(request) && !isPending(request) ? formatDate(new Date(decidedMs(request)).toISOString()) : '—'}</small></td>
                  {/if}
                {/if}
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
    {#if visibleRequests.length > 0}
      <div class="ar-foot">
        <span>{t('{shown} of {total} request(s)', { shown: pageRequests.length, total: visibleRequests.length })}</span>
        {#if pageRequests.length < visibleRequests.length}
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={() => (shown += PAGE)}>{t('Show {count} more', { count: Math.min(PAGE, visibleRequests.length - pageRequests.length) })}</button>
        {/if}
      </div>
    {/if}
  </section>
{#if selectedRequest}
<aside class="b2s-panel ar-side" aria-label={t('Decision')}>
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
      {#if detailLoading}<LoadingState skeleton="detail">{t('Loading full details…')}</LoadingState>{/if}
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

      {#if originalLevel}
        <section>
          <h3>{t('Access level changed')}</h3>
          <p class="ar-level-note">
            {t('First requested: {level}. Changed by {name}: {reason}', {
              level: originalLevel === 'write' ? t('Write') : t('Read'),
              name: selectedRequest.permission_changed_by_display ?? '—',
              reason: selectedRequest.permission_change_reason ?? '—'
            })}
          </p>
        </section>
      {/if}

      {#if canChangeLevel && accessKind(selectedRequest) !== 'other'}
        <section>
          {#if levelEditing}
            <label for="level-reason" class="ar-label">
              {accessKind(selectedRequest) === 'write' ? t('Why read access instead?') : t('Why write access instead?')}
            </label>
            <textarea id="level-reason" class="ar-textarea" maxlength="500" bind:value={levelReason}></textarea>
            <div class="ar-level-actions">
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={levelSaving} on:click={() => { levelEditing = false; levelReason = ''; }}>{t('Cancel')}</button>
              <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={levelSaving || !levelReason.trim()} on:click={changeLevel}>{t('Confirm the change')}</button>
            </div>
          {:else}
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={Boolean(decisionRunning)} on:click={() => (levelEditing = true)}>
              <i class="bi bi-arrow-left-right" aria-hidden="true"></i>
              {accessKind(selectedRequest) === 'write' ? t('Change to read') : t('Change to write')}
            </button>
          {/if}
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
  {#if guardianComment(selectedRequest)}
    <p class="ar-reason"><strong>{statusOf(selectedRequest) === 'rejected' ? t('Reason for the refusal') : t('Comment of the guardian')}</strong>{guardianComment(selectedRequest)}</p>
  {/if}
  <p class="ar-foot-note">
    {#if selectedRequest?.can_cancel}
      {t('You can withdraw this request while it waits for a decision.')}
    {:else if selectedRequest && canReviewSelected && ownRequestBlocked}
      {t('This is your own request: another guardian or an administrator approves it.')}
    {:else if selectedRequest && canReviewSelected}
      {t('You can decide on this request.')}
    {:else if selectedRequest && isPending(selectedRequest)}
      {t('A guardian of this storage root or a platform administrator decides.')}
    {:else if canRevokeSelected}
      {t('Revoking removes the AD group membership now.')}
    {/if}
  </p>
  <div class="ar-foot-actions">
    {#if statusOf(selectedRequest) === 'rejected' && selectedRequest?.own_request && storageRootIdFromRow(selectedRequest) !== null && !selectedRequest?.storage_root_deleted}
      <a class="b2s-btn b2s-btn-secondary" href={`/access-requests/new?root=${storageRootIdFromRow(selectedRequest)}`}>
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>{t('Ask again')}
      </a>
    {/if}
    {#if selectedRequest?.can_cancel}
      <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={cancelling} on:click={() => (showCancelConfirm = true)}>
        <i class="bi bi-x-circle" aria-hidden="true"></i>{cancelling ? t('Cancelling…') : t('Cancel my request')}
      </button>
    {/if}
    {#if canReviewSelected}
      <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={Boolean(decisionRunning)} on:click={() => runDecision('reject')}>
        <i class="bi bi-x-lg" aria-hidden="true"></i>
        {decisionRunning === 'reject' ? t('Rejecting…') : t('Reject')}
      </button>
      <button
        type="button"
        class="b2s-btn b2s-btn-primary"
        disabled={Boolean(decisionRunning) || approvalPreview?.can_approve === false}
        title={ownRequestBlocked ? t('This is your own request: another guardian or an administrator approves it.') : approvalPreview?.can_approve === false ? t('Fix the configuration shown above first') : undefined}
        on:click={() => runDecision('approve')}
      >
        <i class="bi bi-check2" aria-hidden="true"></i>
        {decisionRunning === 'approve' ? t('Approving…') : t('Approve')}
      </button>
    {:else}
      {#if canRevokeSelected && expiresMs(selectedRequest)}
        <button type="button" class="b2s-btn b2s-btn-secondary" disabled={extending} on:click={extendSelected}>
          <i class="bi bi-calendar-plus" aria-hidden="true"></i>{extending ? t('Extending…') : t('Extend by 30 days')}
        </button>
      {/if}
      {#if canRevokeSelected}
        <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={Boolean(decisionRunning)} on:click={() => (showRevokeConfirm = true)}>
          <i class="bi bi-person-x" aria-hidden="true"></i>
          {t('Revoke access')}
        </button>
      {/if}
    {/if}
  </div>
  </div>
  {/if}
</aside>
{/if}
  </div>
</div>

<ConfirmActionModal
  open={showCancelConfirm}
  onClose={() => (showCancelConfirm = false)}
  onConfirm={cancelSelected}
  severity="warning"
  title={t('Cancel this request?')}
  impactItems={[t('The request is withdrawn: nobody will decide on it and nothing changes on the folder.')]}
  confirmLabel={t('Cancel my request')}
/>

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

<ConfirmActionModal
  open={Boolean(bulkDecisionAsked)}
  onClose={() => (bulkDecisionAsked = null)}
  onConfirm={runBulkDecision}
  title={bulkDecisionAsked === 'reject' ? t('Reject {count} requests?', { count: checkedIds.size }) : t('Approve {count} requests?', { count: checkedIds.size })}
  impactItems={[bulkDecisionAsked === 'reject' ? t('The requesters are told their request was refused.') : t('Each person is added to the AD group of the folder.')]}
  severity={bulkDecisionAsked === 'reject' ? 'danger' : 'warning'}
  confirmVariant={bulkDecisionAsked === 'reject' ? 'danger' : 'primary'}
  confirmLabel={bulkDecisionAsked === 'reject' ? t('Reject all') : t('Approve all')}
  confirmBusyLabel={t('Processing {done} of {total}…', { done: bulkDone + 1, total: checkedIds.size })}
  busy={bulkRunning}
/>


<ContextMenu open={Boolean(menu)} title={menu ? requesterName(menu.row) : ''} subtitle={menu ? `${requestCode(menu.row)} · ${resourceName(menu.row)}` : ''}
  items={menu ? menuItems(menu.row) : []} at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pickMenu} />

<style>
  .ar-page {
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: var(--b2s-page-padding);
  }








  .ar-filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }








  .ar-export {
    margin-left: 0;
  }

  /* The selection floats at the bottom of the window: its actions stay in reach while the list scrolls */
  .ar-bulk {
    position: fixed;
    left: 50%;
    bottom: 24px;
    z-index: 40;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 520px;
    padding: 10px 12px 10px 18px;
    border-radius: 18px;
    background: var(--b2s-color-text);
    color: #fff;
    box-shadow: 0 16px 36px rgba(14, 18, 24, 0.28);
    animation: ar-rise 180ms ease-out;
  }
  @keyframes ar-rise { from { opacity: 0; transform: translate(-50%, 12px); } }
  .ar-table tr.is-quick td { background: #F7FCEC; }
  .ar-quick { display: inline-grid; gap: 4px; font-size: var(--b2s-fs-xs); font-weight: 600; color: #3F6212; }
  .ar-quick__bar { display: block; height: 3px; border-radius: 999px; background: #B5F23B; animation: ar-count 5s linear forwards; transform-origin: left; }
  @keyframes ar-count { to { transform: scaleX(0); } }
  .ar-done { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; background: #B5F23B; color: #0E1218; font-size: var(--b2s-fs-xs); font-weight: 700; animation: ar-pulse 1.4s ease-out 2; }
  @keyframes ar-pulse { 0% { box-shadow: 0 0 0 0 rgba(181, 242, 59, 0.75); } 70% { box-shadow: 0 0 0 10px rgba(181, 242, 59, 0); } 100% { box-shadow: 0 0 0 0 rgba(181, 242, 59, 0); } }

  .ar-bulk strong {
    flex: 1;
    font-weight: 600;
  }

  .ar-check {
    width: 44px;
  }

  .ar-body {
    display: flex;
    align-items: flex-start;
    gap: 18px;
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

  .ar-level-note {
    margin: 0;
    color: var(--b2s-text-muted, inherit);
  }

  .ar-level-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
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
  .ar-reason { display: flex; flex-direction: column; gap: 2px; margin: 0 0 10px; padding: 10px 12px; border: 1px solid var(--b2s-color-danger-border, #f0c4c4); border-radius: var(--b2s-radius-md); background: var(--b2s-color-danger-soft); font-size: var(--b2s-fs-sm); }
  .ar-reason strong { color: var(--b2s-color-danger-strong); }
  .ar-counters { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  .ar-counters button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 10px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); text-align: left; cursor: pointer; }
  .ar-counters button.on { border-color: var(--b2s-color-text); box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
  .ar-counters span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ar-counters b { font-size: 22px; font-weight: 600; line-height: 1.2; }
  .ar-counters b.warn { color: var(--b2s-color-warning-strong); }
  .ar-end { min-width: 90px; }
  .ar-bar { display: block; height: 4px; margin-top: 4px; overflow: hidden; border-radius: 99px; background: var(--b2s-color-border-soft, #e9ebf0); }
  .ar-bar span { display: block; height: 4px; background: var(--b2s-color-info); }
  .ar-bar span.soon { background: var(--b2s-color-warning); }
  .ar-dim { color: var(--b2s-color-text-muted); }
  .ar-foot { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--b2s-color-border); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ar-foot span { margin-right: auto; }
  .ar-person small { white-space: nowrap; }
  .ar-filters__end { margin-left: auto; }
</style>
