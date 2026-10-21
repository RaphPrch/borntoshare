<script lang="ts">
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
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

  export let data: { alerts: GovernanceAlert[]; loadFailed: boolean };

  let alerts: GovernanceAlert[] = data.alerts ?? [];
  let loadFailed = data.loadFailed;
  let query = '';
  let statusFilter: 'active' | 'open' | 'acknowledged' | 'resolved' | 'all' = 'active';
  let severityFilter = 'all';
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
      return { label: t('Zone #{id}', { id: alert.zone_id }), href: `/admin/zones/${alert.zone_id}` };
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
    .filter((a) => severityFilter === 'all' || severityOf(a) === severityFilter)
    .filter((a) => {
      const q = normalizeText(query);
      if (!q) return true;
      return normalizeText([a.title, a.message, a.alert_type, scopeOf(a).label].join(' ')).includes(q);
    })
    .sort(
      (a, b) =>
        (SEVERITY_RANK[severityOf(a)] ?? 9) - (SEVERITY_RANK[severityOf(b)] ?? 9) ||
        String(b.last_seen_at ?? '').localeCompare(String(a.last_seen_at ?? ''))
    );
  $: query, statusFilter, severityFilter, (page = 1);
  $: pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);

  async function refresh() {
    refreshing = true;
    try {
      alerts = await listGovernanceAlerts(fetch, { status: 'all' });
      loadFailed = false;
    } catch (error: unknown) {
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

<div class="alerts-page">
  <PageHeader title={t('Alerts')} subtitle={t('Operational issues detected on storage roots, endpoints and identity sources.')}>
    <svelte:fragment slot="actions">
      <button class="b2s-btn b2s-btn-secondary" type="button" on:click={refresh} disabled={refreshing}>
        <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
        {t('Refresh')}
      </button>
    </svelte:fragment>
  </PageHeader>

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
      <option value="critical">{t('Critical')}</option>
      <option value="high">{t('High')}</option>
      <option value="warning">{t('Warning')}</option>
      <option value="info">{t('Info')}</option>
    </select>
  </div>

  {#if loadFailed}
    <InlineAlert tone="error">{t('Unable to load alerts.')}</InlineAlert>
  {/if}

  <section class="b2s-card alerts-table-card">
    {#if filtered.length === 0}
      <EmptyStateInline message={statusFilter === 'active' ? t('No open alert. Everything looks fine.') : t('No alert matches these filters.')} />
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
              <th class="alerts-actions-col"><span class="visually-hidden">{t('Actions')}</span></th>
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
                <td class="alerts-main">
                  <strong>{alert.title ?? alert.alert_type}</strong>
                  {#if alert.message}<small>{alert.message}</small>{/if}
                </td>
                <td>
                  {#if scope.href}<a href={scope.href}>{scope.label}</a>{:else}{scope.label}{/if}
                </td>
                <td class="alerts-date">{formatDateTime(alert.last_seen_at)}</td>
                <td>
                  <StatusBadge compact showDot={false} variant={STATUS_VARIANT[status] ?? 'muted'} label={statusLabel(status)} />
                </td>
                <td class="alerts-actions">
                  {#if status === 'open'}
                    <button
                      class="b2s-btn b2s-btn-secondary b2s-btn-sm"
                      type="button"
                      disabled={busyId !== null}
                      on:click={() => changeStatus(alert, 'acknowledge')}
                    >
                      {t('Acknowledge')}
                    </button>
                  {/if}
                  {#if status !== 'resolved'}
                    <button
                      class="b2s-btn b2s-btn-primary b2s-btn-sm"
                      type="button"
                      disabled={busyId !== null}
                      on:click={() => changeStatus(alert, 'resolve')}
                    >
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
  .alerts-page {
    display: grid;
    gap: 20px;
    padding: var(--b2s-page-padding);
  }

  .alerts-table-card {
    overflow: hidden;
  }

  .alerts-main strong {
    display: block;
    font-weight: 600;
  }

  .alerts-main small {
    display: block;
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .alerts-date {
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .alerts-actions {
    white-space: nowrap;
    text-align: right;
  }

  .alerts-actions .b2s-btn + .b2s-btn {
    margin-left: 8px;
  }

  .alerts-actions-col {
    width: 1%;
  }
</style>
