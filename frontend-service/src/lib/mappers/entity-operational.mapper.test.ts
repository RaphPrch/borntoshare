import assert from 'node:assert/strict';
import {
  buildStorageEndpointOperationalAttentionItems,
  buildZoneOperationalAttentionItems,
  endpointHealthToOperationalTone,
  healthLabelToOperationalTone,
  visualToneToOperationalTone
} from './entity-operational.mapper';

{
  const items = buildZoneOperationalAttentionItems({
    endpointCount: 3,
    reachableCount: 1,
    nonRunnableCount: 1,
    provisioningReady: false,
    healthLabel: 'warning'
  });

  assert.deepEqual(items, [
    '2 endpoints are not reachable.',
    '1 endpoint is missing host and/or credentials.',
    'Provisioning policy is incomplete.'
  ]);
}

{
  const items = buildZoneOperationalAttentionItems({
    endpointCount: 2,
    reachableCount: 2,
    nonRunnableCount: 0,
    provisioningReady: true,
    healthLabel: 'warning'
  });

  assert.deepEqual(items, ['Zone configuration needs review.']);
}

{
  const items = buildStorageEndpointOperationalAttentionItems({
    healthLabel: 'Unreachable',
    hostReady: false,
    pendingRequestCount: 2,
    provisioningWarnings: ['Missing OU', 'Missing OU']
  });

  assert.deepEqual(items, [
    'Endpoint is currently unreachable.',
    'Endpoint host is missing.',
    '2 access requests are waiting for review.',
    'Missing OU'
  ]);
}

assert.equal(healthLabelToOperationalTone('ok'), 'success');
assert.equal(healthLabelToOperationalTone('warning'), 'warning');
assert.equal(endpointHealthToOperationalTone('healthy'), 'success');
assert.equal(endpointHealthToOperationalTone('degraded'), 'warning');
assert.equal(endpointHealthToOperationalTone('unhealthy'), 'danger');
assert.equal(visualToneToOperationalTone('success'), 'success');
assert.equal(visualToneToOperationalTone('error'), 'danger');
assert.equal(visualToneToOperationalTone('warning'), 'warning');
