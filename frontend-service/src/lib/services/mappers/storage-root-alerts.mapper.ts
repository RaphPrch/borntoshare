import type { GovernanceAlert } from '$lib/api/governance-alerts';

export type StorageRootAlertTone = 'warning' | 'error';

export type StorageRootAlertSelectionContext = {
  rootId: number | string | null | undefined;
  selectedRow?: Record<string, unknown> | null;
  overview?: Record<string, unknown> | null;
  globalAlerts?: GovernanceAlert[] | null;
  detailsLoading?: boolean;
};

const toPositiveId = (value: unknown): number => {
  const id = Number(value ?? 0);
  return Number.isFinite(id) && id > 0 ? Math.trunc(id) : 0;
};

const hiddenStorageRootAlertTypes = new Set([
  'acl_principal_not_governed',
  'access_profiles_missing',
  'access_profile_missing',
  'missing_access_profile_binding',
  'ad_group_read_not_created',
  'ad_group_write_not_created',
  'ad_group_not_created',
  'probe_issues',
  'open_issues'
]);
const hiddenStorageRootAlertTitles = new Set([
  'filesystem acl not governed',
  'access profiles missing',
  'access not created',
  'open issues',
  'probe issues'
]);

export const storageRootAlertTone = (alert: GovernanceAlert): StorageRootAlertTone => {
  const explicit = String(alert?.tone ?? '').trim().toLowerCase();
  if (explicit === 'error' || explicit === 'warning') return explicit;

  const severity = String(alert?.severity ?? '').trim().toLowerCase();
  return severity === 'critical' || severity === 'high' ? 'error' : 'warning';
};

export const storageRootAlertRootId = (alert: GovernanceAlert): number =>
  toPositiveId(alert?.storage_root_id ?? alert?.scope_id);

export const isVisibleStorageRootAlert = (alert: GovernanceAlert): boolean => {
  const type = String(alert?.alert_type ?? '').trim().toLowerCase();
  if (hiddenStorageRootAlertTypes.has(type)) return false;
  if (type.includes('access_profile') && (type.includes('missing') || type.includes('binding'))) return false;

  const title = String(alert?.title ?? '').trim().toLowerCase();
  if (hiddenStorageRootAlertTitles.has(title)) return false;
  if (title.includes('access profile') && (title.includes('missing') || title.includes('binding'))) return false;

  const subtitle = String(alert?.subtitle ?? '').trim().toLowerCase();
  if (subtitle.includes('access profile') && (subtitle.includes('missing') || subtitle.includes('binding'))) return false;

  return true;
};

export const visibleStorageRootAlerts = (alerts: GovernanceAlert[] | null | undefined): GovernanceAlert[] =>
  (Array.isArray(alerts) ? alerts : []).filter(isVisibleStorageRootAlert);

export const selectVisibleStorageRootAlertsForRootIds = (
  rootIdsRaw: Array<number | string | null | undefined>,
  alerts: GovernanceAlert[] | null | undefined
): GovernanceAlert[] => {
  const rootIds = new Set(
    (Array.isArray(rootIdsRaw) ? rootIdsRaw : [])
      .map((value) => toPositiveId(value))
      .filter((value) => value > 0)
  );
  if (rootIds.size <= 0) return [];

  return visibleStorageRootAlerts(alerts).filter((alert) => {
    if (String(alert?.status ?? 'open').toLowerCase() !== 'open') return false;
    return rootIds.has(storageRootAlertRootId(alert));
  });
};

export const storageRootAlertSummarySubtitle = (alert: GovernanceAlert): string | null => {
  const type = String(alert?.alert_type ?? '').trim().toLowerCase();
  if (type.includes('ad_group') && (type.includes('not_created') || type.includes('pending'))) {
    return 'No AD group linked';
  }
  if (type === 'endpoint_unreachable') return 'Storage endpoint failed';
  if (type === 'root_probe_failed') return 'Root probe failed';
  if (type.includes('missing_guardian')) return 'No guardian assigned';
  if (type.includes('pending_access_validation')) return 'Access validation pending';
  return null;
};

export const selectOpenStorageRootAlerts = ({
  rootId,
  selectedRow = null,
  overview = null,
  globalAlerts = [],
  detailsLoading = false
}: StorageRootAlertSelectionContext): GovernanceAlert[] => {
  const selectedRootId = toPositiveId(rootId);
  if (selectedRootId <= 0) return [];

  const overviewRootId = toPositiveId(overview?.storage_root_id ?? overview?.id);
  if (!detailsLoading && overviewRootId === selectedRootId && Array.isArray(overview?.governance_alerts)) {
    const overviewAlerts = visibleStorageRootAlerts(overview.governance_alerts as GovernanceAlert[]);
    if (overviewAlerts.length > 0) return overviewAlerts;
  }

  const rowRootId = toPositiveId(selectedRow?.storage_root_id ?? selectedRow?.id);
  if (rowRootId === selectedRootId) {
    const directCount = Number(selectedRow?.open_alerts_count ?? 0);
    if (Number.isFinite(directCount) && directCount <= 0) return [];
  }

  return visibleStorageRootAlerts(globalAlerts).filter((alert) => {
    if (String(alert?.status ?? 'open').toLowerCase() !== 'open') return false;
    return storageRootAlertRootId(alert) === selectedRootId;
  });
};

export const storageRootOpenAlertSummary = (
  row: Record<string, unknown> | null | undefined,
  globalAlerts: GovernanceAlert[] | null | undefined = []
): { count: number; tone: StorageRootAlertTone } | null => {
  if (!row) return null;

  const directCount = Number(row?.open_alerts_count ?? 0);
  if (Number.isFinite(directCount) && directCount <= 0) return null;

  const rootId = toPositiveId(row?.storage_root_id ?? row?.id);
  const relevantGlobalAlerts = (Array.isArray(globalAlerts) ? globalAlerts : []).filter((alert) => {
    if (String(alert?.status ?? 'open').toLowerCase() !== 'open') return false;
    return storageRootAlertRootId(alert) === rootId;
  });
  if (Array.isArray(globalAlerts)) {
    const alerts = visibleStorageRootAlerts(relevantGlobalAlerts);
    if (alerts.length <= 0) return null;
    return {
      count: alerts.length,
      tone: alerts.some((alert) => storageRootAlertTone(alert) === 'error') ? 'error' : 'warning'
    };
  }

  if (Number.isFinite(directCount) && directCount > 0) {
    const errorCount = Number(row?.open_alerts_error_count ?? 0);
    return {
      count: Math.trunc(directCount),
      tone: Number.isFinite(errorCount) && errorCount > 0 ? 'error' : 'warning'
    };
  }

  const alerts = selectOpenStorageRootAlerts({ rootId, selectedRow: row, globalAlerts });
  if (alerts.length <= 0) return null;

  return {
    count: alerts.length,
    tone: alerts.some((alert) => storageRootAlertTone(alert) === 'error') ? 'error' : 'warning'
  };
};
