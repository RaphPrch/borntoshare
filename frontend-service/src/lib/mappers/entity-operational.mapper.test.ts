import assert from 'node:assert/strict';
import {
  buildStorageEndpointOperationalAttentionItems,
  endpointHealthToOperationalTone,
  healthLabelToOperationalTone,
  visualToneToOperationalTone
} from './entity-operational.mapper';

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
