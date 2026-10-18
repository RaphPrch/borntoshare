import {
  deriveAccessRequestBusinessState,
  deriveIdentitySourceBusinessState,
  deriveRootBusinessState,
  mapAccessRequestOverallToVariant,
  normalizeProbeStatus
} from './visual-state.mapper';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testNormalizeProbeStatus(): void {
  assert(normalizeProbeStatus('success') === 'success', 'success should normalize to success');
  assert(normalizeProbeStatus('SUCCEEDED') === 'success', 'SUCCEEDED should normalize to success');
  assert(normalizeProbeStatus('ok') === 'success', 'ok should normalize to success');
  assert(normalizeProbeStatus('passed') === 'success', 'passed should normalize to success');
  assert(normalizeProbeStatus('running') === 'running', 'running should normalize to running');
  assert(normalizeProbeStatus('QUEUED') === 'running', 'QUEUED should normalize to running');
  assert(normalizeProbeStatus('pending') === 'running', 'pending should normalize to running');
  assert(normalizeProbeStatus('failed') === 'failed', 'failed should normalize to failed');
  assert(normalizeProbeStatus('timed-out') === 'failed', 'timed-out should normalize to failed');
  assert(normalizeProbeStatus('cancelled') === 'failed', 'cancelled should normalize to failed');
  assert(normalizeProbeStatus('mystery') === 'unknown', 'unknown value should normalize to unknown');
}

function testRootBusinessState(): void {
  const critical = deriveRootBusinessState({
    persistedProbeStatus: 'success',
    hasAttachedProfiles: true,
    bindingStatus: 'ambiguous',
    hasOwners: true
  });
  assert(critical.overall === 'critical', 'ambiguous binding should be critical');

  const healthy = deriveRootBusinessState({
    persistedProbeStatus: 'success',
    hasAttachedProfiles: true,
    bindingStatus: 'materialized',
    hasOwners: true
  });
  assert(healthy.overall === 'healthy', 'materialized + success + attached should be healthy');
}

function testIdentityBusinessState(): void {
  const disabled = deriveIdentitySourceBusinessState({
    status: 'connected',
    isEnabled: false,
    supportsSnapshot: true
  });
  assert(disabled.overall === 'disabled', 'disabled source should be disabled overall');

  const critical = deriveIdentitySourceBusinessState({
    status: 'error',
    isEnabled: true,
    supportsSnapshot: true,
    snapshotStatus: 'failed'
  });
  assert(critical.overall === 'critical', 'error source/snapshot should be critical overall');
}

function testAccessRequestBusinessState(): void {
  const unknown = deriveAccessRequestBusinessState({ workflowStatus: 'WAT' });
  assert(unknown.overall === 'unknown', 'unknown workflow should remain unknown');
  assert(mapAccessRequestOverallToVariant(unknown.overall) === 'muted', 'unknown request should map to muted');

  const pending = deriveAccessRequestBusinessState({ workflowStatus: 'pending' });
  assert(pending.overall === 'pending', 'pending should remain pending');
  assert(mapAccessRequestOverallToVariant(pending.overall) === 'warning', 'pending should map to warning');
}

async function run(): Promise<void> {
  testNormalizeProbeStatus();
  testRootBusinessState();
  testIdentityBusinessState();
  testAccessRequestBusinessState();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
