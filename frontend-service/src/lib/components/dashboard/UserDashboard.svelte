<script lang="ts">
  import DashboardShell from './DashboardShell.svelte';
  import { accessRequestAccessLabel, accessRequestId, accessRequestRequesterName, accessRequestTargetLabel } from '$lib/services/mappers/access-requests.mapper';
  import { getRequestStatusMeta } from '$lib/utils/access-request-status';
  import { initialsFromLabel } from '$lib/utils/initials';

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

  const formatDateTime = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '—';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return raw;
    return d.toLocaleString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const formatDateTimeCompact = (value: unknown): string => {
    const raw = String(value ?? '').trim();
    if (!raw) return '—';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return raw;
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const requestCode = (row: any): string =>
    String(row?.request_code ?? `REQ-${String(accessRequestId(row)).padStart(6, '0')}`);

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
    if (raw.includes('write') || raw.includes('contribution')) return 'Read & Write';
    if (raw.includes('read')) return 'Read Only';
    return label === '—' ? 'Read Only' : label;
  };

  const statusMeta = (row: any) => {
    const base = getRequestStatusMeta(String(row?.status ?? ''));
    const raw = lower(row?.status);
    if (raw.includes('pending')) {
      return {
        label: row?.is_guardian ? 'Pending guardian' : 'Pending',
        tone: 'pending'
      };
    }
    if (raw.includes('review')) {
      return { label: 'Needs review', tone: 'pending' };
    }
    if (raw.includes('closed') || raw.includes('revoked')) {
      return { label: 'Closed', tone: 'neutral' };
    }
    return base;
  };

  const roleLabel = (row: any): string => {
    const isRequester = row?.is_requester === true;
    const isGuardian = row?.is_guardian === true;
    if (isRequester && isGuardian) return 'Requester + Guardian';
    if (isGuardian) return 'Guardian';
    return 'Requester';
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
  title="User Dashboard"
  subtitle="This page shows only requests where you are the requester or guardian."
>
  <div slot="actions" class="dashboard-actions">
    <a class="new-request-btn" href="/access-requests?create=1">+ New Request</a>
  </div>

  <div class="scope-pill">
    <i class="bi bi-info-circle-fill" aria-hidden="true"></i>
    <span>Visible requests: requester or guardian</span>
  </div>

  <div class="user-dashboard-layout">
    <div class="user-dashboard-main">
      <section class="summary-grid" aria-label="Request summary">
        <article class="summary-card">
          <div class="summary-icon blue"><i class="bi bi-file-earmark-text" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">My Open Requests</div>
            <div class="summary-value">{num(summary.my_open_requests)}</div>
            <div class="summary-subtitle">Awaiting action or decision</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon amber"><i class="bi bi-clock-history" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">Awaiting My Review</div>
            <div class="summary-value">{num(summary.awaiting_my_review)}</div>
            <div class="summary-subtitle">Requests need your review</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon green"><i class="bi bi-check-circle" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">Approved</div>
            <div class="summary-value">{num(summary.approved)}</div>
            <div class="summary-subtitle">Access grants approved</div>
          </div>
        </article>

        <article class="summary-card">
          <div class="summary-icon red"><i class="bi bi-x-circle" aria-hidden="true"></i></div>
          <div class="summary-copy">
            <div class="summary-title">Rejected / Closed</div>
            <div class="summary-value">{num(summary.rejected_or_closed)}</div>
            <div class="summary-subtitle">Requests rejected or closed</div>
          </div>
        </article>
      </section>

      <section class="panel-card">
        <div class="panel-head">
          <div>
            <h2>Requests requiring your action</h2>
            <p>You are listed as guardian for the following requests.</p>
          </div>
          <a class="panel-link" href="/access-requests?status=pending">View all <i class="bi bi-chevron-right" aria-hidden="true"></i></a>
        </div>

        {#if requiresAction.length === 0}
          <div class="empty-state">No request requires your action right now.</div>
        {:else}
          <div class="table-wrap">
            <table class="dashboard-table">
              <thead>
                <tr>
                  <th>Request ID</th>
                  <th>Requester</th>
                  <th>Storage Root</th>
                  <th>Access</th>
                  <th>Status</th>
                  <th>Submitted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {#each requiresAction.slice(0, 5) as row}
                  <tr>
                    <td><a class="request-link" href={requestHref(row, 'pending')}>{requestCode(row)}</a></td>
                    <td>
                      <div class="requester-cell">
                        <span class="avatar">{initialsFromLabel(accessRequestRequesterName(row), 'U')}</span>
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
                    <td><span class="status-badge pending">{statusMeta(row).label}</span></td>
                    <td>{formatDateTime(row?.created_at)}</td>
                    <td><a class="review-btn" href={requestHref(row, 'pending')}>Review</a></td>
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
            <h2>My submitted requests</h2>
          </div>
          <div class="submitted-toolbar">
            <div class="request-tabs" role="tablist" aria-label="Submitted request filters">
              <button type="button" class:active={submittedFilter === 'all'} on:click={() => (submittedFilter = 'all')}>All</button>
              <button type="button" class:active={submittedFilter === 'pending'} on:click={() => (submittedFilter = 'pending')}>Pending</button>
              <button type="button" class:active={submittedFilter === 'approved'} on:click={() => (submittedFilter = 'approved')}>Approved</button>
              <button type="button" class:active={submittedFilter === 'rejected'} on:click={() => (submittedFilter = 'rejected')}>Rejected</button>
            </div>

            <label class="search-box">
              <i class="bi bi-search" aria-hidden="true"></i>
              <input bind:value={searchText} placeholder="Search requests..." aria-label="Search requests" />
            </label>
          </div>
        </div>

        <div class="table-wrap">
          <table class="dashboard-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Storage Root</th>
                <th>Access level</th>
                <th>Status</th>
                <th>Role</th>
                <th>Last update</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {#if filteredSubmittedRequests.length === 0}
                <tr>
                  <td colspan="7" class="empty-row">No submitted request matches the current filter.</td>
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
                    <td><span class={`status-badge ${statusMeta(row).tone}`}>{statusMeta(row).label}</span></td>
                    <td><span class={`role-badge ${roleTone(row)}`}>{roleLabel(row)}</span></td>
                    <td>{formatDateTimeCompact(row?.updated_at ?? row?.created_at)}</td>
                    <td><a class="table-action-link" href={requestHref(row)}>View details</a></td>
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
        <h3>Quick actions</h3>
        <a class="side-action" href="/access-requests?create=1">
          <span class="side-action-icon blue"><i class="bi bi-plus-square" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>Create request</strong><small>Request access to a storage root</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
        <a class="side-action" href="/access-requests">
          <span class="side-action-icon blue"><i class="bi bi-list-task" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>Open all requests</strong><small>View all your requests</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
        <a class="side-action" href="/storage-roots">
          <span class="side-action-icon blue"><i class="bi bi-folder2-open" aria-hidden="true"></i></span>
          <span class="side-action-copy"><strong>View storage roots</strong><small>Browse available storage roots</small></span>
          <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </a>
      </section>

      <section class="side-card">
        <h3>Helpful links</h3>
        <a class="help-link" href="/access-requests">
          <span><strong>How access requests work</strong><small>Learn about the request lifecycle</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
        <a class="help-link" href="/access-requests">
          <span><strong>Access levels explained</strong><small>Understand access levels</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
        <a class="help-link" href="/access-requests">
          <span><strong>Need help?</strong><small>Contact support team</small></span>
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
        </a>
      </section>

      <section class="side-card">
        <h3>Dashboard scope</h3>
        <p>You are viewing requests where you are the requester or a listed guardian.</p>
        <a class="scope-link" href="/access-requests">Learn more about request visibility <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i></a>
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
    border-radius: 12px;
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
    border-radius: 999px;
    background: #eef4ff;
    color: #2563eb;
    font-size: 0.9rem;
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
    border-radius: 16px;
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
    border-radius: 16px;
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
    font-size: 0.95rem;
    font-weight: 700;
  }

  .summary-value {
    color: #111827;
    font-size: 2.1rem;
    line-height: 1.05;
    font-weight: 800;
    margin-top: 6px;
  }

  .summary-subtitle {
    margin-top: 8px;
    color: #64748b;
    font-size: 0.92rem;
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
    font-size: 1.1rem;
    font-weight: 700;
  }

  .panel-head p {
    margin: 6px 0 0;
    color: #64748b;
    font-size: 0.94rem;
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
    font-size: 0.88rem;
    font-weight: 700;
  }

  .dashboard-table td {
    color: #1f2937;
    font-size: 0.93rem;
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
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #dbeafe;
    color: #1d4ed8;
    font-size: 0.8rem;
    font-weight: 700;
    flex: 0 0 30px;
  }

  .status-badge,
  .role-badge {
    display: inline-flex;
    align-items: center;
    min-height: 28px;
    padding: 0 10px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    white-space: nowrap;
  }

  .status-badge.pending { background: #fff4dd; color: #d97706; }
  .status-badge.approved,
  .status-badge.enforced { background: #e7f7eb; color: #2f855a; }
  .status-badge.rejected,
  .status-badge.revoked { background: #fdecec; color: #dc2626; }
  .status-badge.neutral { background: #eef2f7; color: #64748b; }

  .role-badge.requester { background: #eef4ff; color: #2563eb; }
  .role-badge.guardian { background: #f3e8ff; color: #7c3aed; }
  .role-badge.mixed { background: #ede9fe; color: #5b21b6; }

  .review-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    padding: 0 14px;
    border-radius: 10px;
    background: #2563eb;
    color: #fff;
    text-decoration: none;
    font-size: 0.86rem;
    font-weight: 700;
  }

  .empty-state,
  .empty-row {
    color: #64748b;
    font-size: 0.94rem;
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
    border-radius: 10px;
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
    border-radius: 12px;
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
    font-size: 0.92rem;
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
    font-size: 1.02rem;
    font-weight: 700;
  }

  .side-card p {
    margin: 0;
    color: #475569;
    font-size: 0.92rem;
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
    border-radius: 14px;
    padding: 12px 12px;
  }

  .side-action + .side-action,
  .help-link + .help-link {
    margin-top: 10px;
  }

  .side-action-icon {
    width: 36px;
    height: 36px;
    border-radius: 12px;
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
    font-size: 0.93rem;
  }

  .side-action-copy small,
  .help-link small {
    color: #64748b;
    font-size: 0.84rem;
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
