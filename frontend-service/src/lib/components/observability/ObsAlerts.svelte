<script lang="ts">
  import SavedViews from '$lib/components/ui/SavedViews.svelte';
  import { resizableColumns } from '$lib/utils/resizable-columns';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { alertMessage, alertTitle } from '$lib/mappers/storage-root-alerts.mapper';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { t } from '$lib/i18n';
  import { normalizeText } from '$lib/utils/values';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import {
    acknowledgeGovernanceAlert,
    listGovernanceAlerts,
    resolveGovernanceAlert,
    type GovernanceAlert
  } from '$lib/api/governance-alerts';
  import type { StatusVariant } from '$lib/utils/status';
  import { onDestroy, onMount } from 'svelte';
  import { recall, remember } from '$lib/utils/remember';
  import { onLiveChange } from '$lib/stores/live';
  import { listZones } from '$lib/api/zones';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import { alertGuide } from '$lib/components/observability/alert-guides';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { goto } from '$app/navigation';

  /** Opened from the overview: an initial filter (« critical » = critical or high) */
  export let initialSeverity: string = 'all';
  export let initialType: string = '';

  let alerts: GovernanceAlert[] = [];
  let loadFailed = false;
  let loading = true;
  let query = initialType;
  // A link with a severity or a type opens that view; otherwise the list reopens as it was left
  const fromLink = Boolean(initialType) || (initialSeverity || 'all') !== 'all';
  const saved = recall('alerts', { statusFilter: 'active', zoneFilter: 'all', grouped: true, pageSize: 25 });
  let statusFilter = (fromLink ? 'active' : saved.statusFilter) as 'active' | 'open' | 'acknowledged' | 'resolved' | 'all';
  let severityFilter = initialSeverity || 'all';
  let zoneFilter = fromLink ? 'all' : saved.zoneFilter;
  // By type first: a filter coming from the overview shows the alerts themselves
  let grouped = fromLink ? false : saved.grouped;
  let zones: { id: number; name: string }[] = [];
  let page = 1;
  let pageSize = saved.pageSize;
  $: remember('alerts', { statusFilter, zoneFilter, grouped, pageSize });
  let busyId: string | null = null;
  let refreshing = false;

  const SEVERITY_RANK: Record<string, number> = { critical: 1, high: 2, warning: 3, info: 4 };
  const SEVERITY_VARIANT: Record<string, StatusVariant> = { critical: 'error', high: 'error', warning: 'warning', info: 'info' };
  const STATUS_VARIANT: Record<string, StatusVariant> = { open: 'warning', acknowledged: 'info', resolved: 'success' };

  const severityOf = (alert: GovernanceAlert) => String(alert.severity ?? 'info').toLowerCase();
  const statusOf = (alert: GovernanceAlert) => String(alert.status ?? 'open').toLowerCase();

  // Labels are translated when read
  const severityLabel = (value: string): string =>
    ({ critical: t('Critical'), high: t('High'), warning: t('Warning'), info: t('Info') })[value] ?? value;
  const statusLabel = (value: string): string =>
    ({ open: t('New'), acknowledged: t('Acknowledged'), resolved: t('Resolved') })[value] ?? value;

  const scopeOf = (alert: GovernanceAlert): { label: string; href: string | null } => {
    const meta = (alert.metadata_json ?? {}) as Record<string, unknown>;
    if (alert.storage_root_id) {
      return {
        label: String(meta.storage_root_name ?? t('Storage root #{id}', { id: alert.storage_root_id })),
        href: `/storage-roots?selected=${alert.storage_root_id}`
      };
    }
    if (alert.storage_endpoint_id) {
      return {
        label: String(meta.storage_endpoint_name ?? t('Storage endpoint #{id}', { id: alert.storage_endpoint_id })),
        href: `/admin/storage-endpoints/${alert.storage_endpoint_id}`
      };
    }
    if (alert.identity_source_id) {
      return { label: t('Identity source #{id}', { id: alert.identity_source_id }), href: '/admin/identity-sources' };
    }
    if (alert.zone_id) {
      return { label: zones.find((z) => String(z.id) === String(alert.zone_id))?.name ?? t('Zone #{id}', { id: alert.zone_id }), href: `/admin/zones/${alert.zone_id}` };
    }
    return { label: String(alert.scope_type ?? '—'), href: null };
  };

  $: active = alerts.filter((a) => statusOf(a) !== 'resolved');
  $: counts = {
    critical: active.filter((a) => ['critical', 'high'].includes(severityOf(a)) && statusOf(a) === 'open').length,
    warning: active.filter((a) => severityOf(a) === 'warning' && statusOf(a) === 'open').length,
    acknowledged: active.filter((a) => statusOf(a) === 'acknowledged').length,
    resolved: alerts.filter((a) => statusOf(a) === 'resolved').length
  };
  $: filtered = alerts
    .filter((a) => {
      const status = statusOf(a);
      if (statusFilter === 'active') return status !== 'resolved';
      return statusFilter === 'all' || status === statusFilter;
    })
    .filter((a) =>
      severityFilter === 'all' ||
      (severityFilter === 'critical_high' ? ['critical', 'high'].includes(severityOf(a)) : severityOf(a) === severityFilter)
    )
    .filter((a) => zoneFilter === 'all' || String(a.zone_id ?? '') === zoneFilter)
    .filter((a) => {
      const q = normalizeText(query);
      if (!q) return true;
      return normalizeText([a.title, a.message, typeOf(a), scopeOf(a).label].join(' ')).includes(q);
    })
    .sort(
      (a, b) =>
        (SEVERITY_RANK[severityOf(a)] ?? 9) - (SEVERITY_RANK[severityOf(b)] ?? 9) ||
        String(b.last_seen_at ?? '').localeCompare(String(a.last_seen_at ?? ''))
    );
  $: query, statusFilter, severityFilter, zoneFilter, grouped, (page = 1);
  $: pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);

  /** « Endpoint unreachable × 86 »: one line per type, worst severity first */
  $: groups = Object.values(
    filtered.reduce<Record<string, { type: string; title: string; severity: string; count: number; scopes: string[]; lastSeen: string }>>((acc, a) => {
      const type = typeOf(a);
      const group = (acc[type] ??= { type, title: a.title ? alertTitle(a) : type, severity: severityOf(a), count: 0, scopes: [], lastSeen: '' });
      group.count += 1;
      if ((SEVERITY_RANK[severityOf(a)] ?? 9) < (SEVERITY_RANK[group.severity] ?? 9)) group.severity = severityOf(a);
      const scope = scopeOf(a).label;
      if (scope && !group.scopes.includes(scope)) group.scopes.push(scope);
      if (String(a.last_seen_at ?? '') > group.lastSeen) group.lastSeen = String(a.last_seen_at ?? '');
      return acc;
    }, {})
  ).sort((a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9) || b.count - a.count);
  $: groupRows = groups.slice((page - 1) * pageSize, page * pageSize);

  function typeOf(alert: GovernanceAlert): string {
    return String(alert.alert_type ?? 'other').split(':')[0];
  }

  function showGroup(type: string) {
    grouped = false;
    query = type;
  }

  onMount(async () => {
    await refresh();
    loading = false;
    zones = (await listZones(fetch).catch(() => []))
      .map((z) => ({ id: Number(z.id), name: String(z.name ?? z.id) }))
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  // An alert raised or closed elsewhere: the list follows without a click
  onDestroy(onLiveChange((state) => state.alertsStamp, () => { if (!refreshing && busyId === null) void refresh(); }));

  async function refresh() {
    refreshing = true;
    try {
      alerts = await listGovernanceAlerts(fetch, { status: 'all' });
      loadFailed = false;
    } catch (error: unknown) {
      loadFailed = true;
      reportUiError(error, 'Unable to load alerts.', 'alerts.refresh');
    } finally {
      refreshing = false;
    }
  }

  // « Resolve » opens how to fix the cause first: marking it resolved alone does not fix anything
  let guideAlert: GovernanceAlert | null = null;
  $: guide = guideAlert ? alertGuide(guideAlert.alert_type) : null;
  $: guideScope = guideAlert ? scopeOf(guideAlert) : null;
  $: guideHref = guideScope?.href && guide?.action?.tab ? `${guideScope.href}&tab=${guide.action.tab}` : guideScope?.href ?? null;
  async function resolveFromGuide() {
    if (!guideAlert) return;
    const alert = guideAlert;
    await changeStatus(alert, 'resolve');
    guideAlert = null;
  }

  // ---- right click on an alert: the row's actions plus the object it concerns ----
  let menu: { alert: GovernanceAlert; at: { x: number; y: number } } | null = null;
  function openMenu(alert: GovernanceAlert, event: MouseEvent) {
    event.preventDefault();
    menu = { alert, at: menuPositionFor(event) };
  }
  function menuItems(alert: GovernanceAlert): ContextMenuItem[] {
    const status = statusOf(alert);
    const scope = scopeOf(alert);
    return [
      { key: 'ack', label: t('Acknowledge'), icon: 'bi-eye', disabled: status !== 'open' || busyId !== null, hint: status !== 'open' ? t('Already taken care of') : undefined },
      { key: 'resolve', label: t('How to resolve it'), icon: 'bi-check2-circle', disabled: status === 'resolved' || busyId !== null },
      { key: 'open', label: scope.href ? t('Open {name}', { name: scope.label }) : t('No object to open'), icon: 'bi-box-arrow-up-right', disabled: !scope.href, separated: true },
      { key: 'copy', label: t('Copy the message'), icon: 'bi-clipboard' }
    ];
  }
  function pickMenu(key: string) {
    const alert = menu?.alert;
    if (!alert) return;
    if (key === 'ack') void changeStatus(alert, 'acknowledge');
    else if (key === 'resolve') guideAlert = alert;
    else if (key === 'open') { const href = scopeOf(alert).href; if (href) void goto(href); }
    else if (key === 'copy') {
      const text = [alert.title ? alertTitle(alert) : alert.alert_type, alert.message ? alertMessage(alert) : ''].filter(Boolean).join(' — ');
      void navigator.clipboard?.writeText(text).then(() => toast.success(t('Message copied.')));
    }
  }

  async function changeStatus(alert: GovernanceAlert, action: 'acknowledge' | 'resolve') {
    const id = String(alert.id ?? '');
    if (!id || busyId) return;
    busyId = id;
    try {
      if (action === 'acknowledge') {
        await acknowledgeGovernanceAlert(fetch, id);
        toast.success(t('Alert acknowledged.'));
      } else {
        await resolveGovernanceAlert(fetch, id);
        toast.success(t('Alert resolved.'));
      }
      await refresh();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to update the alert.', `alerts.${action}`);
    } finally {
      busyId = null;
    }
  }
</script>

<div class="obs-alerts">
  <section class="b2s-kpi-grid" aria-label={t('Alerts summary')}>
    <KpiCard label={t('Critical or high')} value={counts.critical} icon="bi-exclamation-octagon" tone="danger" />
    <KpiCard label={t('Warnings')} value={counts.warning} icon="bi-exclamation-triangle" tone="warning" />
    <KpiCard label={t('Acknowledged alerts')} value={counts.acknowledged} icon="bi-eye" tone="info" />
    <KpiCard label={t('Resolved alerts')} value={counts.resolved} icon="bi-check2-circle" tone="success" />
  </section>

  <div class="b2s-toolbar">
    <SearchField wrapperClass="b2s-toolbar__search" placeholder={t('Search alerts…')} ariaLabel={t('Search alerts')} bind:value={query} />
    <select class="b2s-select" bind:value={statusFilter} aria-label={t('Status')}>
      <option value="active">{t('New and acknowledged')}</option>
      <option value="open">{t('New')}</option>
      <option value="acknowledged">{t('Acknowledged')}</option>
      <option value="resolved">{t('Resolved')}</option>
      <option value="all">{t('All statuses')}</option>
    </select>
    <select class="b2s-select" bind:value={severityFilter} aria-label={t('Severity')}>
      <option value="all">{t('All severities')}</option>
      <option value="critical_high">{t('Critical or high')}</option>
      <option value="critical">{t('Critical')}</option>
      <option value="high">{t('High')}</option>
      <option value="warning">{t('Warning')}</option>
      <option value="info">{t('Info')}</option>
    </select>
    <select class="b2s-select" bind:value={zoneFilter} aria-label={t('Zone')}>
      <option value="all">{t('All zones')}</option>
      {#each zones as zone (zone.id)}<option value={String(zone.id)}>{zone.name}</option>{/each}
    </select>
    <label class="obs-toggle">
      <input type="checkbox" class="obs-switch" bind:checked={grouped} />
      <span>{t('Group by type')}</span>
    </label>
    <button class="b2s-btn b2s-btn-secondary b2s-toolbar__end" type="button" on:click={refresh} disabled={refreshing}>
      <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
      {t('Refresh')}
    </button>
  </div>
  <div class="obs-views">
    <SavedViews key="alerts" current={{ statusFilter, severityFilter, zoneFilter, query, grouped }}
      apply={(view) => { statusFilter = (view.statusFilter ?? 'active') as typeof statusFilter; severityFilter = String(view.severityFilter ?? 'all'); zoneFilter = String(view.zoneFilter ?? 'all'); query = String(view.query ?? ''); grouped = Boolean(view.grouped); }} />
  </div>

  {#if loadFailed}
    <InlineAlert tone="error">{t('Unable to load alerts.')}</InlineAlert>
  {/if}

  <section class="b2s-card obs-card">
    {#if loading}
      <LoadingState skeleton="rows" />
    {:else if filtered.length === 0}
      <EmptyStateInline message={statusFilter === 'active' && !query && severityFilter === 'all' && zoneFilter === 'all' ? t('No open alert. Everything looks fine.') : t('No alert matches these filters.')}
        actionLabel={statusFilter !== 'active' || query || severityFilter !== 'all' || zoneFilter !== 'all' ? t('Clear the filters') : null} actionIcon="bi-x-circle"
        onAction={() => { statusFilter = 'active'; query = ''; severityFilter = 'all'; zoneFilter = 'all'; }} />
    {:else if grouped}
      <div class="b2s-table-wrap">
        <table class="b2s-table" use:resizableColumns={'alerts'}>
          <thead>
            <tr>
              <th>{t('Severity')}</th>
              <th>{t('Alert')}</th>
              <th class="obs-num">{t('Count')}</th>
              <th>{t('Affected items')}</th>
              <th>{t('Last seen')}</th>
              <th class="obs-actions-col"><span class="visually-hidden">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {#each groupRows as group (group.type)}
              <tr>
                <td><StatusBadge compact variant={SEVERITY_VARIANT[group.severity] ?? 'muted'} label={severityLabel(group.severity)} /></td>
                <td class="obs-main"><strong>{group.title}</strong><small>{group.type}</small></td>
                <td class="obs-num"><strong>× {group.count}</strong></td>
                <td>{group.scopes.slice(0, 3).join(', ')}{group.scopes.length > 3 ? ` +${group.scopes.length - 3}` : ''}</td>
                <td class="obs-date"><RelativeTime value={group.lastSeen} /></td>
                <td class="obs-actions">
                  <button class="b2s-btn b2s-btn-secondary b2s-btn-sm" type="button" on:click={() => showGroup(group.type)}>{t('Show')}</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <Pagination total={groups.length} bind:page bind:pageSize />
    {:else}
      <div class="b2s-table-wrap">
        <table class="b2s-table" use:resizableColumns={'alerts'}>
          <thead>
            <tr>
              <th>{t('Severity')}</th>
              <th>{t('Alert')}</th>
              <th>{t('Affected item')}</th>
              <th>{t('Last seen')}</th>
              <th>{t('Status')}</th>
              <th class="obs-actions-col"><span class="visually-hidden">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {#each pageRows as alert (alert.id)}
              {@const scope = scopeOf(alert)}
              {@const status = statusOf(alert)}
              <tr on:contextmenu={(event) => openMenu(alert, event)}>
                <td>
                  <StatusBadge compact variant={SEVERITY_VARIANT[severityOf(alert)] ?? 'muted'} label={severityLabel(severityOf(alert))} />
                </td>
                <td class="obs-main">
                  <strong>{alert.title ? alertTitle(alert) : alert.alert_type}</strong>
                  {#if alert.message}<small>{alertMessage(alert)}</small>{/if}
                </td>
                <td>
                  {#if scope.href}<a href={scope.href}>{scope.label}</a>{:else}{scope.label}{/if}
                </td>
                <td class="obs-date"><RelativeTime value={alert.last_seen_at} /></td>
                <td>
                  <StatusBadge compact showDot={false} variant={STATUS_VARIANT[status] ?? 'muted'} label={statusLabel(status)} />
                </td>
                <td class="obs-actions">
                  {#if status === 'open'}
                    <button class="b2s-btn b2s-btn-secondary b2s-btn-sm" type="button" title={t('I have seen it and I am dealing with it: the alert stays, marked as taken care of')} disabled={busyId !== null} on:click={() => changeStatus(alert, 'acknowledge')}>
                      {t('Acknowledge')}
                    </button>
                  {/if}
                  {#if status !== 'resolved'}
                    <button class="b2s-btn b2s-btn-primary b2s-btn-sm" type="button" disabled={busyId !== null} on:click={() => (guideAlert = alert)}>
                      {t('Resolve')}
                    </button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <Pagination total={filtered.length} bind:page bind:pageSize />
    {/if}
  </section>
</div>

<AppModal open={guideAlert !== null} onClose={() => (guideAlert = null)} size="lg" iconClass="bi bi-tools"
  title={guideAlert ? (guideAlert.title ? alertTitle(guideAlert) : String(guideAlert.alert_type ?? '')) : ''}
  subtitle={guideScope?.label ?? null}>
  {#if guideAlert && guide}
    <div class="guide">
      {#if guideAlert.message}<p class="guide__msg">{alertMessage(guideAlert)}</p>{/if}
      <h3>{t('Why this alert')}</h3>
      <p>{guide.cause}</p>
      <h3>{t('How to resolve it')}</h3>
      <ol>{#each guide.steps as step}<li>{step}</li>{/each}</ol>
      <p class="guide__note"><i class="bi bi-info-circle" aria-hidden="true"></i>
        {t('The checks close the alert by themselves once the cause is gone. Marking it resolved by hand hides it until the next check: if the cause is still there, it opens again.')}</p>
    </div>
  {/if}
  <svelte:fragment slot="footer-start">
    {#if guideHref}<a class="b2s-btn b2s-btn-secondary" href={guideHref}>{guide?.action?.label ?? t('Open the item')}</a>{/if}
  </svelte:fragment>
  <svelte:fragment slot="footer">
    <button class="b2s-btn b2s-btn-secondary" type="button" on:click={() => (guideAlert = null)}>{t('Cancel')}</button>
    <button class="b2s-btn b2s-btn-primary" type="button" disabled={busyId !== null} on:click={resolveFromGuide}>{t('It is fixed: mark resolved')}</button>
  </svelte:fragment>
</AppModal>

<ContextMenu open={Boolean(menu)} title={menu ? (menu.alert.title ? alertTitle(menu.alert) : String(menu.alert.alert_type ?? '')) : ''} subtitle={menu ? scopeOf(menu.alert).label : ''}
  items={menu ? menuItems(menu.alert) : []} at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={pickMenu} />

<style>
  .obs-alerts {
    display: grid;
    gap: 16px;
  }

  .obs-card {
    overflow: hidden;
  }

  .obs-main strong {
    display: block;
    font-weight: 600;
  }

  .obs-main small {
    display: block;
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .obs-date {
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .obs-num {
    text-align: right;
    white-space: nowrap;
  }

  .obs-actions {
    white-space: nowrap;
    text-align: right;
  }

  .obs-actions .b2s-btn + .b2s-btn {
    margin-left: 8px;
  }

  .obs-actions-col {
    width: 1%;
  }

  .obs-toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-strong);
    cursor: pointer;
    white-space: nowrap;
  }

  .obs-switch {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-border-mid);
    position: relative;
    cursor: pointer;
    transition: background 0.16s ease;
  }

  .obs-switch::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: var(--b2s-color-surface);
    transition: transform 0.16s ease;
  }

  .obs-switch:checked {
    background: var(--b2s-topbar-bg, #0b1530);
  }

  .obs-switch:checked::after {
    transform: translateX(15px);
  }
  .guide { display: flex; flex-direction: column; gap: 6px; font-size: var(--b2s-fs-sm); }
  .guide h3 { margin: 10px 0 0; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .guide p, .guide ol { margin: 0; }
  .guide ol { padding-left: 20px; display: flex; flex-direction: column; gap: 4px; }
  .guide__msg { padding: 8px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft, #f6f7f9); color: var(--b2s-color-text-muted); }
  .guide__note { display: flex; gap: 8px; margin-top: 10px !important; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .obs-views { margin: -4px 0 12px; }
</style>
