<script lang="ts">
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime, initials } from '$lib/utils/format';
  import DashboardShell from './DashboardShell.svelte';
  import { accessRequestAccessLabel, accessRequestId, accessRequestRequesterName, accessRequestTargetLabel } from '$lib/mappers/access-requests.mapper';
  import { getRequestStatusMeta, requestToneVariant } from '$lib/utils/access-request-status';

  export let data: any;

  const summary = data?.summary ?? {};
  const requiresAction = Array.isArray(data?.requires_action) ? data.requires_action : [];
  const visibleRequests = Array.isArray(data?.visible_requests) ? data.visible_requests : [];

  let submittedFilter: 'all' | 'pending' | 'approved' | 'rejected' = 'all';
  let searchText = '';

  const num = (value: unknown): number => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const lower = (value: unknown): string => String(value ?? '').trim().toLowerCase();

  const requestCode = (row: any): string =>
    String(row?.request_code ?? t('REQ-{value}', { value: (String(accessRequestId(row)).padStart(6, '0')) }));

  const requestHref = (row: any, status: 'pending' | 'all' = 'all'): string => {
    const id = accessRequestId(row);
    const params = new URLSearchParams();
    params.set('request', String(id));
    params.set('status', status);
    return `/access-requests?${params.toString()}`;
  };

  const normalizedAccess = (row: any): string => {
    const label = accessRequestAccessLabel(row);
    const raw = lower(label);
    if (raw.includes('write') || raw.includes('contribution')) return t('Read & Write');
    if (raw.includes('read')) return t('Read Only');
    return label === '—' ? t('Read Only') : label;
  };

  const statusMeta = (row: any) => {
    const base = getRequestStatusMeta(String(row?.status ?? ''));
    const raw = lower(row?.status);
    if (raw.includes('pending')) {
      return {
        label: row?.is_guardian ? t('Pending guardian') : t('Pending'),
        tone: 'pending'
      };
    }
    if (raw.includes('review')) {
      return { label: t('Needs review'), tone: 'pending' };
    }
    if (raw.includes('closed') || raw.includes('revoked')) {
      return { label: t('Closed'), tone: 'neutral' };
    }
    return base;
  };

  const roleLabel = (row: any): string => {
    const isRequester = row?.is_requester === true;
    const isGuardian = row?.is_guardian === true;
    if (isRequester && isGuardian) return t('Requester + Guardian');
    if (isGuardian) return t('Guardian');
    return t('Requester');
  };

  const roleTone = (row: any): 'requester' | 'guardian' | 'mixed' => {
    const isRequester = row?.is_requester === true;
    const isGuardian = row?.is_guardian === true;
    if (isRequester && isGuardian) return 'mixed';
    if (isGuardian) return 'guardian';
    return 'requester';
  };

  const submittedRequests = visibleRequests.filter((row: any) => row?.is_requester === true);

  const matchSubmittedFilter = (row: any): boolean => {
    if (submittedFilter === 'all') return true;
    const raw = lower(row?.status);
    if (submittedFilter === 'pending') return raw.includes('pending') || raw.includes('review');
    if (submittedFilter === 'approved') return raw.includes('approved') || raw.includes('enforced');
    return raw.includes('rejected') || raw.includes('revoked') || raw.includes('closed');
  };

  const matchSearch = (row: any): boolean => {
    const q = lower(searchText);
    if (!q) return true;
    return [
      requestCode(row),
      accessRequestTargetLabel(row),
      normalizedAccess(row),
      roleLabel(row),
      statusMeta(row).label
    ]
      .map(lower)
      .join(' ')
      .includes(q);
  };

  $: filteredSubmittedRequests = submittedRequests.filter((row: any) => matchSubmittedFilter(row) && matchSearch(row));
</script>

<DashboardShell
  title={t('User Dashboard')}
  subtitle={t('This page shows only requests where you are the requester or guardian.')}
>
  <div slot="actions" class="dashboard-actions">
    <a class="new-request-btn" href="/access-requests?create=1">{t('+ New Request')}</a>
  </div>

  <div class="scope-pill">
    <i class="bi bi-info-circle-fill" aria-hidden="true"></i>
    <span>{t('Visible requests: requester or guardian')}</span>
  </div>

  <div class="user-dashboard-layout">
    <div class="user-dashboard-main">
      <section class="summary-grid" aria-label={t('Request summary')}>
        <article class="summary-card">
          <div class="summary-icon blue"><i class="bi bi-file-earmark-text" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">{t('My Open Requests')}</div>
            <div class="summary-value">{num(summary.my_open_requests)}</div>
            <div class="summary-subtitle">{t('Awaiting action or decision')}</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon amber"><i class="bi bi-clock-history" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">{t('Awaiting My Review')}</div>
            <div class="summary-value">{num(summary.awaiting_my_review)}</div>
            <div class="summary-subtitle">{t('Requests need your review')}</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon green"><i class="bi bi-check-circle" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">{t('Approved')}</div>
            <div class="summary-value">{num(summary.approved)}</div>
            <div class="summary-subtitle">{t('Access grants approved')}</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon red"><i class="bi bi-x-circle" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">{t('Rejected / Closed')}</div>
            <div class="summary-value">{num(summary.rejected_or_closed)}</div>
            <div class="summary-subtitle">{t('Requests rejected or closed')}</div>
          </div>
        </article>
      </section>

      <section class="panel-card">
        <div class="panel-head">
          <div>
            <h2>{t('Requests requiring your action')}</h2>
            <p>{t('You are listed as guardian for the following requests.')}</p>
          </div>
          <a class="panel-link" href="/access-requests?status=pending">{t('View all')} <i class="bi bi-chevron-right" aria-hidden="true"></i></a>
        </div>

        {#if requiresAction.length === 0}
          <div class="empty-state">{t('No request requires your action right now.')}</div>
        {:else}
          <div class="table-wrap">
            <table class="dashboard-table">
              <thead>
                <tr>
                  <th>{t('Request ID')}</th>
                  <th>{t('Requester')}</th>
                  <th>{t('Storage Root')}</th>
                  <th>{t('Access')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Submitted')}</th>
                  <th>{t('Action')}</th>
                </tr>
              </thead>
              <tbody>
                {#each requiresAction.slice(0, 5) as row}
                  <tr>
                    <td><a class="request-link" href={requestHref(row, 'pending')}>{requestCode(row)}</a></td>
                    <td>
                      <div class="requester-cell">
                        <span class="avatar">{initials(accessRequestRequesterName(row), 'U')}</span>
                        <span>{accessRequestRequesterName(row)}</span>
                      </div>
                    </td>
                    <td>
                      <div class="root-cell">
                        <i class="bi bi-folder" aria-hidden="true"></i>
                        <span>{accessRequestTargetLabel(row)}</span>
                      </div>
                    </td>
                    <td>{normalizedAccess(row)}</td>
                    <td><StatusBadge compact variant="warning" label={statusMeta(row).label} /></td>
                    <td>{formatDateTime(row?.created_at)}</td>
                    <td><a class="review-btn" href={requestHref(row, 'pending')}>{t('Review')}</a></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </section>

      <section class="panel-card">
        <div class="panel-head panel-head--stack">
          <div>
            <h2>{t('My submitted requests')}</h2>
          </div>
          <div class="submitted-toolbar">
            <div class="request-tabs" role="tablist" aria-label={t('Submitted request filters')}>
              <button type="button" class:active={submittedFilter === 'all'} on:click={() => (submittedFilter = 'all')}>{t('All')}</button>
              <button type="button" class:active={submittedFilter === 'pending'} on:click={() => (submittedFilter = 'pending')}>{t('Pending')}</button>
              <button type="button" class:active={submittedFilter === 'approved'} on:click={() => (submittedFilter = 'approved')}>{t('Approved')}</button>
              <button type="button" class:active={submittedFilter === 'rejected'} on:click={() => (submittedFilter = 'rejected')}>{t('Rejected')}</button>
            </div>

            <label class="search-box">
              <i class="bi bi-search" aria-hidden="true"></i>
              <input bind:value={searchText} placeholder={t('Search requests...')} aria-label={t('Search requests')} />
            </label>
          </div>
        </div>

        <div class="table-wrap">
          <table class="dashboard-table">
            <thead>
              <tr>
                <th>{t('Request ID')}</th>
                <th>{t('Storage Root')}</th>
                <th>{t('Access level')}</th>
                <th>{t('Status')}</th>
                <th>{t('Role')}</th>
                <th>{t('Last update')}</th>
                <th>{t('Actions')}</th>
              </tr>
            </thead>
            <tbody>
              {#if filteredSubmittedRequests.length === 0}
                <tr>
                  <td colspan="7" class="empty-row">{t('No submitted request matches the current filter.')}</td>
                </tr>
              {:else}
                {#each filteredSubmittedRequests.slice(0, 8) as row}
                  <tr>
                    <td><a class="request-link" href={requestHref(row)}>{requestCode(row)}</a></td>
                    <td>
                      <div class="root-cell">
                        <i class="bi bi-folder" aria-hidden="true"></i>
                        <span>{accessRequestTargetLabel(row)}</span>
                      </div>
                    </td>
                    <td>{normalizedAccess(row)}</td>
                    <td><StatusBadge compact variant={requestToneVariant(statusMeta(row).tone)} label={statusMeta(row).label} /></td>
                    <td><span class={`role-badge ${roleTone(row)}`}>{roleLabel(row)}</span></td>
                    <td>{formatDateTime(row?.updated_at ?? row?.created_at)}</td>
                    <td><a class="table-action-link" href={requestHref(row)}>{t('View details')}</a></td>
                  </tr>
                {/each}
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <aside class="user-dashboard-sidebar">
      <section class="side-card">
        <h3>{t('Quick actions')}</h3>
        <a class="side-action" href="/access-requests?create=1">
          <span class="side-action-icon blue"><i class="bi bi-plus-square" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>{t('Create request')}</strong><small>{t('Request access to a storage root')}</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
        <a class="side-action" href="/access-requests">
          <span class="side-action-icon blue"><i class="bi bi-list-task" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>{t('Open all requests')}</strong><small>{t('View all your requests')}</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
        <a class="side-action" href="/storage-roots">
          <span class="side-action-icon blue"><i class="bi bi-folder2-open" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>{t('View storage roots')}</strong><small>{t('Browse available storage roots')}</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
      </section>

      <section class="side-card">
        <h3>{t('Helpful links')}</h3>
        <a class="help-link" href="/access-requests">
          <span><strong>{t('How access requests work')}</strong><small>{t('Learn about the request lifecycle')}</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
        <a class="help-link" href="/access-requests">
          <span><strong>{t('Access levels explained')}</strong><small>{t('Understand access levels')}</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
        <a class="help-link" href="/access-requests">
          <span><strong>{t('Need help?')}</strong><small>{t('Contact support team')}</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
      </section>

      <section class="side-card">
        <h3>{t('Dashboard scope')}</h3>
        <p>{t('You are viewing requests where you are the requester or a listed guardian.')}</p>
        <a class="scope-link" href="/access-requests">{t('Learn more about request visibility')} <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i></a>
      </section>
    </aside>
  </div>
</DashboardShell>

<style>
  :global(.b2s-dashboard) {
    background: #f5f7fb;
    min-height: 100%;
  }

  .dashboard-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .new-request-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 16px;
    border-radius: var(--b2s-radius-md);
    background: #0b1d63;
    color: #fff;
    text-decoration: none;
    font-weight: 700;
    border: 1px solid #0b1d63;
  }

  .scope-pill {
    width: fit-content;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: var(--b2s-radius-pill);
    background: #eef4ff;
    color: #2563eb;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .user-dashboard-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 18px;
    align-items: start;
  }

  .user-dashboard-main {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
  }

  .summary-card,
  .panel-card,
  .side-card {
    background: #fff;
    border: 1px solid #e5eaf3;
    border-radius: var(--b2s-radius-lg);
    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  }

  .summary-card {
    padding: 20px;
    display: flex;
    gap: 16px;
    align-items: center;
    min-height: 118px;
  }

  .summary-icon {
    width: 56px;
    height: 56px;
    border-radius: var(--b2s-radius-lg);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    flex: 0 0 56px;
  }

  .summary-icon.blue { background: #eaf2ff; color: #3b82f6; }
  .summary-icon.amber { background: #fff4dd; color: #f59e0b; }
  .summary-icon.green { background: #e8f8ea; color: #65a30d; }
  .summary-icon.red { background: #fdeaea; color: #ef4444; }

  .summary-copy {
    min-width: 0;
  }

  .summary-title {
    color: #243253;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .summary-value {
    color: #111827;
    font-size: var(--b2s-fs-console-title);
    line-height: 1.05;
    font-weight: 800;
    margin-top: 6px;
  }

  .summary-subtitle {
    margin-top: 8px;
    color: #64748b;
    font-size: var(--b2s-fs-md);
  }

  .panel-card {
    padding: 18px;
  }

  .panel-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .panel-head--stack {
    flex-direction: column;
  }

  .panel-head h2 {
    margin: 0;
    color: #0f172a;
    font-size: var(--b2s-fs-xl);
    font-weight: 700;
  }

  .panel-head p {
    margin: 6px 0 0;
    color: #64748b;
    font-size: var(--b2s-fs-lg);
  }

  .panel-link,
  .table-action-link,
  .request-link,
  .scope-link {
    color: #2563eb;
    text-decoration: none;
    font-weight: 600;
  }

  .table-wrap {
    overflow-x: auto;
  }

  .dashboard-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 760px;
  }

  .dashboard-table th,
  .dashboard-table td {
    padding: 14px 12px;
    border-bottom: 1px solid #edf1f7;
    text-align: left;
    vertical-align: middle;
  }

  .dashboard-table th {
    color: #475569;
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .dashboard-table td {
    color: #1f2937;
    font-size: var(--b2s-fs-md);
  }

  .requester-cell,
  .root-cell {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .root-cell i {
    color: #64748b;
  }

  .avatar {
    width: 30px;
    height: 30px;
    border-radius: var(--b2s-radius-pill);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #dbeafe;
    color: #1d4ed8;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    flex: 0 0 30px;
  }
  .role-badge {
    display: inline-flex;
    align-items: center;
    min-height: 28px;
    padding: 0 10px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    white-space: nowrap;
  }

  .role-badge.requester { background: #eef4ff; color: #2563eb; }
  .role-badge.guardian { background: #f3e8ff; color: #7c3aed; }
  .role-badge.mixed { background: #ede9fe; color: #5b21b6; }

  .review-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: var(--b2s-radius-md);
    background: #2563eb;
    color: #fff;
    text-decoration: none;
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .empty-state,
  .empty-row {
    color: #64748b;
    font-size: var(--b2s-fs-lg);
    text-align: center;
    padding: 18px 12px;
  }

  .submitted-toolbar {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    flex-wrap: wrap;
  }

  .request-tabs {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .request-tabs button {
    min-height: 34px;
    padding: 0 12px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid transparent;
    background: transparent;
    color: #334155;
    font-weight: 600;
  }

  .request-tabs button.active {
    background: #eef4ff;
    border-color: #cfe0ff;
    color: #2563eb;
  }

  .search-box {
    min-width: 280px;
    height: 40px;
    border: 1px solid #dbe3ef;
    border-radius: var(--b2s-radius-md);
    background: #fff;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 12px;
    color: #64748b;
  }

  .search-box input {
    width: 100%;
    border: 0;
    outline: 0;
    background: transparent;
    color: #0f172a;
    font-size: var(--b2s-fs-md);
  }

  .user-dashboard-sidebar {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .side-card {
    padding: 18px;
  }

  .side-card h3 {
    margin: 0 0 14px;
    color: #0f172a;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .side-card p {
    margin: 0;
    color: #475569;
    font-size: var(--b2s-fs-md);
    line-height: 1.5;
  }

  .side-action,
  .help-link {
    display: flex;
    align-items: center;
    gap: 12px;
    text-decoration: none;
    color: inherit;
  }

  .side-action {
    border: 1px solid #e8edf5;
    border-radius: var(--b2s-radius-lg);
    padding: 12px 12px;
  }

  .side-action + .side-action,
  .help-link + .help-link {
    margin-top: 10px;
  }

  .side-action-icon {
    width: 36px;
    height: 36px;
    border-radius: var(--b2s-radius-md);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 36px;
  }

  .side-action-icon.blue {
    background: #eef4ff;
    color: #2563eb;
  }

  .side-action-copy,
  .help-link span {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1 1 auto;
  }

  .side-action-copy strong,
  .help-link strong {
    color: #0f172a;
    font-size: var(--b2s-fs-md);
  }

  .side-action-copy small,
  .help-link small {
    color: #64748b;
    font-size: var(--b2s-fs-sm);
  }

  .help-link {
    justify-content: space-between;
    padding: 2px 0;
  }

  .scope-link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
  }

  @media (max-width: 1320px) {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 1100px) {
    .user-dashboard-layout {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 720px) {
    .summary-grid {
      grid-template-columns: 1fr;
    }

    .submitted-toolbar {
      align-items: stretch;
    }

    .search-box {
      min-width: 0;
      width: 100%;
    }
  }
</style>
