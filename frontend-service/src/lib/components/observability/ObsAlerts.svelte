<script lang="ts">
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
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
  import { onMount } from 'svelte';
  import { listZones } from '$lib/api/zones';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';

  /** Opened from the overview: an initial filter (« critical » = critical or high) */
  export let initialSeverity: string = 'all';
  export let initialType: string = '';

  let alerts: GovernanceAlert[] = [];
  let loadFailed = false;
  let loading = true;
  let query = initialType;
  let statusFilter: 'active' | 'open' | 'acknowledged' | 'resolved' | 'all' = 'active';
  let severityFilter = initialSeverity || 'all';
  let zoneFilter = 'all';
  let grouped = false;
  let zones: { id: number; name: string }[] = [];
  let page = 1;
  let pageSize = 25;
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
      const group = (acc[type] ??= { type, title: String(a.title ?? type), severity: severityOf(a), count: 0, scopes: [], lastSeen: '' });
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

  {#if loadFailed}
    <InlineAlert tone="error">{t('Unable to load alerts.')}</InlineAlert>
  {/if}

  <section class="b2s-card obs-card">
    {#if loading}
      <LoadingState />
    {:else if filtered.length === 0}
      <EmptyStateInline message={statusFilter === 'active' ? t('No open alert. Everything looks fine.') : t('No alert matches these filters.')} />
    {:else if grouped}
      <div class="b2s-table-wrap">
        <table class="b2s-table">
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
                <td class="obs-date">{formatDateTime(group.lastSeen)}</td>
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
        <table class="b2s-table">
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
              <tr>
                <td>
                  <StatusBadge compact variant={SEVERITY_VARIANT[severityOf(alert)] ?? 'muted'} label={severityLabel(severityOf(alert))} />
                </td>
                <td class="obs-main">
                  <strong>{alert.title ?? alert.alert_type}</strong>
                  {#if alert.message}<small>{alert.message}</small>{/if}
                </td>
                <td>
                  {#if scope.href}<a href={scope.href}>{scope.label}</a>{:else}{scope.label}{/if}
                </td>
                <td class="obs-date">{formatDateTime(alert.last_seen_at)}</td>
                <td>
                  <StatusBadge compact showDot={false} variant={STATUS_VARIANT[status] ?? 'muted'} label={statusLabel(status)} />
                </td>
                <td class="obs-actions">
                  {#if status === 'open'}
                    <button class="b2s-btn b2s-btn-secondary b2s-btn-sm" type="button" disabled={busyId !== null} on:click={() => changeStatus(alert, 'acknowledge')}>
                      {t('Acknowledge')}
                    </button>
                  {/if}
                  {#if status !== 'resolved'}
                    <button class="b2s-btn b2s-btn-primary b2s-btn-sm" type="button" disabled={busyId !== null} on:click={() => changeStatus(alert, 'resolve')}>
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
    color: #334155;
    cursor: pointer;
    white-space: nowrap;
  }

  .obs-switch {
    appearance: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: #cbd5e1;
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
    background: #ffffff;
    transition: transform 0.16s ease;
  }

  .obs-switch:checked {
    background: var(--b2s-topbar-bg, #0b1530);
  }

  .obs-switch:checked::after {
    transform: translateX(15px);
  }
</style>
