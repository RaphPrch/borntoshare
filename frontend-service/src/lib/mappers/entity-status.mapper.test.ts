import {
  probeStatusLabel,
  probeStatusVariant,
  rootAvailabilityLabel,
  rootAvailabilityVariant
} from './entity-status.mapper';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testProbeStatusPresentation(): void {
  assert(probeStatusLabel('QUEUED') === 'Running', 'queued probe should render Running');
  assert(probeStatusVariant('ok') === 'success', 'ok probe should render success');
  assert(probeStatusVariant('timed-out') === 'error', 'timed-out probe should render error');
  assert(probeStatusLabel('wat') === 'Unknown', 'unknown probe should render Unknown');
}

function testRootAvailabilityPresentation(): void {
  assert(rootAvailabilityLabel('reachable') === 'Reachable', 'reachable root should render Reachable');
  assert(rootAvailabilityVariant('reachable') === 'success', 'reachable root should render success');
  assert(rootAvailabilityLabel('blocked_by_endpoint') === 'Endpoint blocked', 'blocked root label mismatch');
  assert(rootAvailabilityVariant('blocked_by_endpoint') === 'error', 'blocked root should render error');
  assert(rootAvailabilityLabel('needs_root_probe') === 'Root probe needed', 'needs_root_probe label mismatch');
  assert(rootAvailabilityVariant('needs_root_probe') === 'warning', 'needs_root_probe should render warning');
}

testProbeStatusPresentation();
testRootAvailabilityPresentation();
