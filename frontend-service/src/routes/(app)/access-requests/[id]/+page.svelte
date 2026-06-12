<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { getRequestStatusMeta, isProvisioningInFlight } from '$lib/utils/access-request-status';
  import { bulkDecision } from '$lib/api/access-requests';
  import { apiGetData } from '$lib/api/client';
  import { toast } from '$lib/utils/toast';
  import { initialsFromLabel } from '$lib/utils/initials';
  import { mapAccessRequestDecisionErrorFromBulk, type AccessRequestDecisionUiError } from '$lib/utils/request-decision-errors';
  import {
    accessProfileLabel,
    requestEvents,
    boolLabel,
    daysLeft,
    displayName,
    firstNonEmpty,
    formatDateTime,
    requestId,
    storageRootIdFromRequest,
    storageRootLabel,
    timelinePercent,
    toBoolean,
    ttlCountdownLabel
  } from './request-detail.helpers';

  export let data: { mode: 'dal'; request: any };

  let req: any = data.request;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let actionRunning: 'approve' | 'reject' | 'revoke' | null = null;
  let actionMenuOpen = false;
  let decisionInlineError: AccessRequestDecisionUiError | null = null;

  const initials = (value?: string | null) => initialsFromLabel(value, '??');

  $: requestStatus = String(req?.status ?? '').toLowerCase();
  $: canApprove = requestStatus === 'pending';
  $: canReject = requestStatus === 'pending';
  $: canRevoke = requestStatus === 'approved' || requestStatus === 'enforced';
  $: statusMeta = getRequestStatusMeta(req?.status);
  $: requestCode = req?.request_code ?? `REQ-${requestId(req, data?.request)}`;
  $: userLabel = String(displayName(req));
  $: storageLabel = String(storageRootLabel(req));
  $: accessLabel = String(accessProfileLabel(req));
  $: expiresAtLabel = req?.expires_at ? formatDateTime(req.expires_at) : '—';
  $: daysRemaining = daysLeft(req);
  $: progressPercent = timelinePercent(req);
  $: requestTimeline = requestEvents(req);
  $: ttlCountdown = ttlCountdownLabel(req);

  $: justificationRequired = toBoolean(
    firstNonEmpty([
      req?.justification_required,
      req?.governance?.justification_required,
      req?.policy?.justification_required
    ])
  );

  $: ttlEnforced = toBoolean(
    firstNonEmpty([
      req?.ttl_enforced,
      req?.governance?.ttl_enforced,
      req?.policy?.ttl_enforced,
      Number(req?.ttl_days ?? 0) > 0 ? true : null,
      req?.expires_at ? true : null
    ])
  );

  $: sensitivityZone =
    firstNonEmpty([
      req?.sensitivity_zone,
      req?.zone_name,
      req?.zone,
      req?.storage_root_zone,
      req?.governance?.zone
    ]) ?? '—';

  $: riskLevel =
    firstNonEmpty([
      req?.risk_level,
      req?.risk?.level,
      req?.impact_level,
      req?.governance?.risk_level
    ]) ?? '—';

  $: appliedViaGroup =
    firstNonEmpty([
      req?.ad_group,
      req?.applied_via_group,
      req?.principal_group,
      req?.grant_group,
      req?.group_name
    ]) ?? '—';

  $: expectedAdGroup =
    firstNonEmpty([
      req?.expected_ad_group,
      req?.expected_group_name
    ]) ?? '—';

  async function refreshRequest() {
    const id = requestId(req, data?.request);
    if (!id) return;
    try {
      req = await apiGetData<any>(fetch, `/access-requests/${id}`);
    } catch {
      // silent refresh failure
    }
  }

  async function runDecision(decision: 'approve' | 'reject' | 'revoke') {
    const id = requestId(req, data?.request);
    if (!id || actionRunning) return;

    actionRunning = decision;
    try {
      const result = await bulkDecision(fetch, [id], decision);
      const failed = Number(result?.failed_ids?.length ?? 0);
      const started = Number(result?.executions_started ?? 0);
      decisionInlineError = null;

      if (failed > 0) {
        if (decision === 'approve') {
          const mapped = mapAccessRequestDecisionErrorFromBulk(result, {
            fallbackStorageRootId: storageRootIdFromRequest(req)
          });
          decisionInlineError = mapped.showInlineNotice ? mapped : null;
          if (mapped.severity === 'warning') {
            toast.warning(`${mapped.title} · ${mapped.message}`);
          } else {
            toast.error(`${mapped.title} · ${mapped.message}`);
          }
          if (mapped.hint) {
            toast.info(mapped.hint);
          }
          if (mapped.actionHref) {
            toast.info(`Open storage root access: ${mapped.actionHref}`);
          }
        } else {
          const actionLabel = `Action ${decision}`;
          toast.error(`${actionLabel} failed`);
        }
      } else {
        decisionInlineError = null;
        const capsuleMsg = decision === 'approve' ? ` · ${started} capsule(s) started` : '';
        toast.success(`Action ${decision} applied${capsuleMsg}`);
      }
      await refreshRequest();
    } catch {
      toast.error(`Action ${decision} failed`);
    } finally {
      actionRunning = null;
      actionMenuOpen = false;
    }
  }

  $: if (req && isProvisioningInFlight(req?.provisioning ?? [])) {
    if (!pollTimer) {
      pollTimer = setInterval(() => {
        refreshRequest();
      }, 3000);
    }
  } else if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  onMount(() => {
    req = data.request;
  });

  onDestroy(() => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  });
</script>

<svelte:head>
  <title>Access request details</title>
</svelte:head>

{#if !req}
  <section class="b2s-page">
    <h1 class="b2s-title">Request not found</h1>
    <a class="b2s-btn-secondary" href="/access-requests">Back</a>
  </section>
{:else}
  <section class="ar-page">
    <header class="ar-header-row">
      <div class={`ar-status-chip ${statusMeta.tone}`}>
        <i class="bi bi-shield-check"></i>
        {statusMeta.label.toUpperCase()}
      </div>
      <h1>{requestCode}</h1>
      <div class="ar-actions">
        <div class="menu-wrap">
          <button class="btn btn-action" type="button" on:click={() => (actionMenuOpen = !actionMenuOpen)}>
            <i class="bi bi-three-dots-vertical"></i>
            Actions
            <i class="bi bi-chevron-down"></i>
          </button>
          {#if actionMenuOpen}
            <div class="menu-popover">
              <button type="button" on:click={() => runDecision('revoke')} disabled={!canRevoke || Boolean(actionRunning)}>
                <i class="bi bi-file-earmark-lock2"></i>
                Revoke Access
              </button>
              <button type="button" disabled>
                <i class="bi bi-envelope-paper"></i>
                Extend TTL
              </button>
              <button type="button" disabled>
                <i class="bi bi-terminal"></i>
                Rerun capsule
              </button>
              <button type="button" disabled>
                <i class="bi bi-search"></i>
                View audit log
              </button>
              <button type="button" disabled>
                <i class="bi bi-file-earmark-text"></i>
                Export audit (PDF)
              </button>
            </div>
          {/if}
        </div>
        {#if canRevoke}
          <button class="btn btn-danger" type="button" disabled={Boolean(actionRunning)} on:click={() => runDecision('revoke')}>
            Revoke Access
          </button>
        {:else if canApprove || canReject}
          <button class="btn btn-primary" type="button" disabled={!canApprove || Boolean(actionRunning)} on:click={() => runDecision('approve')}>
            Approve
          </button>
          <button class="btn btn-danger" type="button" disabled={!canReject || Boolean(actionRunning)} on:click={() => runDecision('reject')}>
            Reject
          </button>
        {/if}
      </div>
    </header>

    {#if decisionInlineError && decisionInlineError.showInlineNotice}
      <section class="ar-inline-alert" role="status" aria-live="polite">
        <div class="ar-inline-alert__title">{decisionInlineError.title}</div>
        <div class="ar-inline-alert__text">
          {decisionInlineError.inlinePrimary ?? decisionInlineError.message}
        </div>
        {#if decisionInlineError.inlineSecondary}
          <div class="ar-inline-alert__text ar-inline-alert__text--muted">{decisionInlineError.inlineSecondary}</div>
        {/if}
        {#if decisionInlineError.actionHref}
          <a class="ar-inline-alert__link" href={decisionInlineError.actionHref}>
            {decisionInlineError.actionLabel ?? 'Open storage root'}
          </a>
        {/if}
      </section>
    {/if}

    <div class="ar-grid">
      <section class="ar-card ar-journey">
        <div class="journey-head">
          <div class="identity-line">
            <div class="avatar b2s-persona b2s-persona--lg">{initials(userLabel)}</div>
            <div class="name">{userLabel}</div>
            <i class="bi bi-arrow-right"></i>
            <div class="scope-pill"><i class="bi bi-folder2"></i> {storageLabel}</div>
          </div>
          <div class="ttl-tag">{daysRemaining} days</div>
        </div>
        <div class="journey-bar-wrap">
          <div class="journey-bar">
            <span class="fill" style={`width:${progressPercent}%`}></span>
          </div>
          <div class="journey-end">{daysRemaining} days</div>
        </div>
        <div class="journey-meta">
          <span>{formatDateTime(req?.created_at)}</span>
          <span>Expired at</span>
          <span class="pct">{progressPercent}%</span>
        </div>
      </section>

      <section class="ar-card ar-left">
        <h3>Request Summary</h3>
        <div class="sub-card">
          <div class="sub-title">Access granted</div>
          <div class="soft-box">
            <div class="strong">{accessLabel}</div>
            <div class="muted-row">Expected AD group: <strong>{expectedAdGroup}</strong></div>
            <div class="muted-row">Applied via AD group: <strong>{appliedViaGroup}</strong></div>
          </div>
        </div>

        <div class="sub-card">
          <div class="sub-title">Time-to-Live (TTL)</div>
          <div class="muted-row">Expires: <strong>{expiresAtLabel}</strong></div>
          <div class="ttl-bar">{ttlCountdown} <i class="bi bi-chevron-right"></i></div>
          <button class="btn btn-primary small" type="button" disabled>Extend TTL</button>
        </div>

        <div class="sub-card requester">
          <div class="sub-title">Requestor</div>
          <div class="identity-row">
            <span class="mini-avatar b2s-persona b2s-persona--xs">{initials(userLabel)}</span>
            <strong>{userLabel}</strong>
          </div>
        </div>
      </section>

      <div class="ar-center-col">
        <section class="ar-card">
          <h3>Governance Summary</h3>
          <div class="governance-box">
            <div class="line"><span>{boolLabel(justificationRequired, 'Justification required', 'Justification optional')}</span>{#if justificationRequired === true}<i class="bi bi-check2"></i>{/if}</div>
            <div class="line"><span>{boolLabel(ttlEnforced, 'TTL enforced', 'TTL not enforced')}</span>{#if ttlEnforced === true}<i class="bi bi-check2"></i>{/if}</div>
            <div class="line"><span>Sensitivity zone</span><strong>{sensitivityZone}</strong></div>
            <div class="line line-last"><span>Risk level</span><strong class="warn">{riskLevel}</strong></div>
            <div class="actions-row">
              <button class="btn btn-primary small" type="button" disabled>Extend TTL</button>
            </div>
          </div>
        </section>

      </div>

      <div class="ar-right-col">
        <section class="ar-card">
          <h3>Request Timeline</h3>
          <div class="timeline-v2">
            {#each requestTimeline as step}
              <div class="step">
                <div class="dot-wrap"><span class={`dot ${step.success ? 'ok' : ''}`}></span></div>
                <div class="step-card">
                  <strong>{step.title}</strong>
                  <span>{step.date ? formatDateTime(step.date) : '—'}</span>
                </div>
              </div>
            {/each}
          </div>
        </section>

      </div>
    </div>
  </section>
{/if}

<style>
  :global(.b2s-app-root main) {
    padding: 0 !important;
  }

  .ar-page {
    min-height: calc(100vh - 64px);
    background: #edf1f7;
    color: #1f2a44;
    padding: 14px 18px 18px;
  }

  .ar-header-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 14px;
    margin-bottom: 12px;
  }

  .ar-header-row h1 {
    margin: 0;
    font-size: 30px;
    letter-spacing: -0.02em;
    font-weight: 600;
    color: #2a3652;
  }

  .ar-status-chip {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    border-radius: 14px;
    padding: 10px 16px;
    border: 1px solid rgba(15, 23, 42, 0.1);
    font-size: 14px;
    font-weight: 800;
    line-height: 1;
    background: #dbeafe;
    color: #1d4ed8;
    text-transform: uppercase;
  }

  .ar-status-chip i {
    font-size: 14px;
  }

  .ar-status-chip.approved,
  .ar-status-chip.enforced {
    background: linear-gradient(180deg, #4da574, #379564);
    color: #eefdf3;
    border-color: rgba(22, 101, 52, 0.32);
  }

  .ar-status-chip.pending {
    background: linear-gradient(180deg, #f4ca63, #eeb445);
    color: #5e3b00;
  }

  .ar-status-chip.rejected,
  .ar-status-chip.revoked {
    background: linear-gradient(180deg, #ec7a7a, #df4d4d);
    color: #fff;
  }

  .ar-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    position: relative;
  }

  .btn {
    border-radius: 14px;
    border: 1px solid #c9d3e1;
    background: #f8fafc;
    color: #1f2a44;
    padding: 8px 14px;
    font-size: 14px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 10px;
    line-height: 1.25;
  }

  .btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .btn-action {
    background: linear-gradient(180deg, #fbfcfe, #eef3f8);
  }

  .btn-primary {
    background: linear-gradient(180deg, #4a8ddf, #2f72c9);
    border-color: #2f72c9;
    color: #ffffff;
  }

  .btn-danger {
    background: linear-gradient(180deg, #df6768, #cd5455);
    border-color: #bf4c4d;
    color: #ffffff;
  }

  .btn.small {
    font-size: 13px;
    padding: 6px 12px;
    border-radius: 10px;
  }

  .menu-wrap {
    position: relative;
  }

  .menu-popover {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    width: 272px;
    border: 1px solid #d4dbe7;
    border-radius: 16px;
    background: #ffffff;
    box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14);
    z-index: 40;
    padding: 10px;
  }

  .menu-popover button {
    width: 100%;
    border: none;
    background: transparent;
    text-align: left;
    padding: 12px 10px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #1f2a44;
    font-size: 14px;
  }

  .menu-popover button + button {
    border-top: 1px solid #edf1f7;
  }

  .menu-popover button:disabled {
    opacity: 0.7;
  }

  .ar-grid {
    display: grid;
    grid-template-columns: minmax(280px, 1.05fr) minmax(420px, 1.45fr) minmax(320px, 1.2fr);
    grid-template-areas:
      'journey journey journey'
      'left center right';
    gap: 10px;
    align-items: start;
  }

  .ar-inline-alert {
    margin: 0 0 12px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(180, 83, 9, 0.32);
    background: rgba(251, 191, 36, 0.12);
    color: #78350f;
  }

  .ar-inline-alert__title {
    font-size: 13px;
    font-weight: 800;
    margin-bottom: 4px;
  }

  .ar-inline-alert__text {
    font-size: 13px;
    line-height: 1.35;
  }

  .ar-inline-alert__text--muted {
    margin-top: 2px;
    color: #92400e;
  }

  .ar-inline-alert__link {
    margin-top: 6px;
    display: inline-flex;
    font-size: 13px;
    color: #1d4ed8;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .ar-card {
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid #d7deeb;
    border-radius: 18px;
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
    overflow: hidden;
    height: fit-content;
  }

  .ar-card h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    line-height: 1.2;
    color: #1f2a44;
    padding: 10px 14px;
    border-bottom: 1px solid #e5ebf4;
  }

  .ar-journey {
    grid-area: journey;
    padding: 10px 14px 10px;
  }

  .journey-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .identity-line {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    font-size: 16px;
    font-weight: 700;
  }

  .avatar {
    box-shadow: none;
  }

  .scope-pill {
    background: #edf1f6;
    border: 1px solid #dce3ef;
    padding: 7px 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .ttl-tag {
    font-size: 14px;
    color: #5b6f8c;
    font-weight: 500;
  }

  .journey-bar-wrap {
    position: relative;
    margin-bottom: 10px;
  }

  .journey-bar {
    height: 6px;
    border-radius: 999px;
    background: #d9e8de;
    overflow: hidden;
  }

  .journey-bar .fill {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: #9ccfb3;
  }

  .journey-end {
    position: absolute;
    right: 0;
    top: -12px;
    background: #edf1f6;
    border: 1px solid #dce3ef;
    border-radius: 12px;
    padding: 5px 12px;
    color: #364962;
    font-size: 14px;
    font-weight: 600;
  }

  .journey-meta {
    color: #617492;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 12px;
  }

  .journey-meta .pct {
    border: 1px solid #cfd8e6;
    background: #f0f4f9;
    border-radius: 999px;
    padding: 1px 7px;
    color: #334155;
    font-weight: 600;
  }

  .ar-left {
    grid-area: left;
  }

  .sub-card {
    padding: 10px 14px;
    border-bottom: 1px solid #e6edf7;
  }

  .sub-card:last-child {
    border-bottom: none;
  }

  .sub-title {
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 10px;
    color: #1f2a44;
  }

  .soft-box {
    border: 1px solid #dde4f0;
    border-radius: 12px;
    background: #fbfcfe;
    padding: 10px 12px;
  }

  .strong {
    font-size: 14px;
    color: #243552;
    margin-bottom: 8px;
  }

  .muted-row {
    font-size: 13px;
    color: #5c6f8b;
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .ttl-bar {
    margin-top: 8px;
    border: 1px solid #dde4f0;
    border-radius: 12px;
    background: #eef2f7;
    padding: 7px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 14px;
    color: #31425d;
    margin-bottom: 8px;
  }

  .identity-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    color: #1f2a44;
  }

  .mini-avatar {
    font-size: 10px;
    box-shadow: none;
  }

  .ar-center-col {
    grid-area: center;
    display: grid;
    gap: 10px;
    align-content: start;
  }

  .governance-box {
    padding: 10px 14px 12px;
  }

  .governance-box .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    color: #2d3d58;
    font-size: 13px;
    padding: 5px 0;
    line-height: 1.3;
  }

  .governance-box .line i {
    color: #52ad7f;
    font-size: 14px;
  }

  .line-last {
    border-top: 1px solid #e7edf7;
    margin-top: 5px;
    padding-top: 8px;
  }

  .warn {
    color: #d97706;
  }

  .actions-row {
    display: flex;
    justify-content: flex-end;
    margin-top: 6px;
  }

  .ar-right-col {
    grid-area: right;
    display: grid;
    align-content: start;
    gap: 10px;
  }

  .timeline-v2 {
    padding: 8px 10px 10px;
  }

  .step {
    display: grid;
    grid-template-columns: 20px 1fr;
    gap: 8px;
    position: relative;
    margin-bottom: 8px;
  }

  .step:last-child {
    margin-bottom: 0;
  }

  .dot-wrap {
    position: relative;
  }

  .dot-wrap::after {
    content: '';
    position: absolute;
    left: 8px;
    top: 16px;
    bottom: -12px;
    width: 2px;
    background: #c6dfd1;
  }

  .step:last-child .dot-wrap::after {
    display: none;
  }

  .dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #cbd5e1;
    border: 2px solid #ffffff;
    box-shadow: 0 0 0 1px #b7c4d8;
    display: inline-block;
  }

  .dot.ok {
    background: #4ba87c;
  }

  .step-card {
    border: 1px solid #dde4f0;
    border-radius: 10px;
    background: #fbfcfe;
    padding: 8px 10px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    font-size: 13px;
    color: #334861;
  }

  .step-card strong {
    color: #1f2a44;
  }

  .step-card span {
    color: #334861;
    font-size: 13px;
  }

  @media (max-width: 1320px) {
    .ar-grid {
      grid-template-columns: 1fr 1fr;
      grid-template-areas:
        'journey journey'
        'left center'
        'right right';
    }

    .ar-header-row h1 {
      font-size: 26px;
    }
  }

  @media (max-width: 900px) {
    .ar-page {
      padding: 16px;
    }

    .ar-header-row {
      grid-template-columns: 1fr;
      align-items: start;
    }

    .ar-grid {
      grid-template-columns: 1fr;
      grid-template-areas:
        'journey'
        'left'
        'center'
        'right';
    }

    .ar-status-chip {
      font-size: 13px;
    }

    .ar-header-row h1 {
      font-size: 24px;
    }

    .btn {
      font-size: 13px;
    }

    .sub-title,
    .ar-card h3,
    .step-card,
    .governance-box .line,
    .identity-line,
    .ttl-bar,
    .strong,
    .muted-row,
    .scope-pill,
    .journey-end,
    .journey-meta {
      font-size: 13px;
    }
  }
</style>
