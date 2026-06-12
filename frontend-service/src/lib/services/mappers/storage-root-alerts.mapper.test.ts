import {
  selectOpenStorageRootAlerts,
  selectVisibleStorageRootAlertsForRootIds,
  storageRootAlertSummarySubtitle,
  storageRootAlertTone,
  storageRootOpenAlertSummary
} from './storage-root-alerts.mapper';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testOverviewEmptyAlertsFallBackToVisibleGlobalAlerts(): void {
  const alerts = selectOpenStorageRootAlerts({
    rootId: 10,
    selectedRow: { storage_root_id: 10, open_alerts_count: 4 },
    overview: { storage_root_id: 10, governance_alerts: [] },
    globalAlerts: [
      { id: 1, storage_root_id: 10, status: 'open', alert_type: 'root_probe_failed', severity: 'critical' }
    ],
    detailsLoading: false
  });

  assert(alerts.length === 1, 'selected overview governance_alerts=[] should fall back to visible global alerts for the same root');
}

function testSelectedRootDoesNotReusePreviousRootAlerts(): void {
  const alerts = selectOpenStorageRootAlerts({
    rootId: 20,
    selectedRow: { storage_root_id: 20, open_alerts_count: 0 },
    overview: { storage_root_id: 10, governance_alerts: [
      { id: 1, storage_root_id: 10, status: 'open', alert_type: 'root_probe_failed', severity: 'critical' }
    ] },
    globalAlerts: [
      { id: 1, storage_root_id: 10, status: 'open', alert_type: 'root_probe_failed', severity: 'critical' }
    ],
    detailsLoading: true
  });

  assert(alerts.length === 0, 'root with open_alerts_count=0 must not reuse previous root alerts while loading');
}

function testGlobalAlertsAreFilteredByRootId(): void {
  const alerts = selectOpenStorageRootAlerts({
    rootId: 30,
    selectedRow: { storage_root_id: 30, open_alerts_count: 2 },
    globalAlerts: [
      { id: 1, storage_root_id: 10, status: 'open', alert_type: 'root_probe_failed', severity: 'critical' },
      { id: 2, storage_root_id: 30, status: 'open', alert_type: 'missing_guardian', severity: 'warning' },
      { id: 4, scope_id: 30, status: 'open', alert_type: 'ad_group_read_not_created', severity: 'high' }
    ]
  });

  assert(alerts.length === 1, 'global alerts should include only visible open alerts for the selected root');
  assert(alerts.every((alert) => Number(alert.storage_root_id ?? alert.scope_id) === 30), 'global alert filter leaked another root');
}

function testSummaryTone(): void {
  const summary = storageRootOpenAlertSummary(
    { storage_root_id: 40, open_alerts_count: 0 },
    [
      { id: 1, storage_root_id: 40, status: 'open', severity: 'warning' },
      { id: 2, storage_root_id: 40, status: 'open', severity: 'high' }
    ]
  );

  assert(summary === null, 'direct open_alerts_count=0 should be authoritative for rows');
  assert(storageRootAlertTone({ severity: 'critical' }) === 'error', 'critical should map to error');
  assert(storageRootAlertTone({ severity: 'warning' }) === 'warning', 'warning should map to warning');
}

function testVisibleAlertsForRootIdsHideLegacyAlerts(): void {
  const alerts = selectVisibleStorageRootAlertsForRootIds(
    [50],
    [
      { id: 1, storage_root_id: 50, status: 'open', alert_type: 'missing_guardian', severity: 'warning' },
      { id: 2, storage_root_id: 50, status: 'open', alert_type: 'access_profiles_missing', severity: 'high' }
    ]
  );

  assert(alerts.length === 1, 'legacy hidden alerts should not be counted in visible aggregate filters');
  assert(storageRootAlertSummarySubtitle({ alert_type: 'missing_guardian' }) === 'No guardian assigned', 'missing_guardian subtitle should stay explicit');
}

function testSummaryIgnoresDirectCountWhenVisibleGlobalAlertsAreClean(): void {
  const summary = storageRootOpenAlertSummary(
    { storage_root_id: 60, open_alerts_count: 3, open_alerts_error_count: 1 },
    [
      { id: 1, storage_root_id: 60, status: 'open', alert_type: 'access_profiles_missing', severity: 'high' },
      { id: 2, storage_root_id: 60, status: 'resolved', alert_type: 'root_probe_failed', severity: 'critical' }
    ]
  );

  assert(summary === null, 'hidden or resolved global alerts should not fall back to stale direct counters');
}

testOverviewEmptyAlertsFallBackToVisibleGlobalAlerts();
testSelectedRootDoesNotReusePreviousRootAlerts();
testGlobalAlertsAreFilteredByRootId();
testSummaryTone();
testVisibleAlertsForRootIdsHideLegacyAlerts();
testSummaryIgnoresDirectCountWhenVisibleGlobalAlertsAreClean();
