import assert from 'node:assert/strict';
import { STATE_META, capacityLine, topologyHref, topologyLevel } from './storage-topology';

const at = (query: string) => topologyLevel(new URLSearchParams(query));

// Navigation: each level needs the one above; the address goes back to the same place
assert.deepEqual(at(''), { zone: null, server: null, dfs: null, volume: null, share: null });
assert.deepEqual(at('zone=3&server=12&share=/fs/finance&volume=d:'), { zone: 3, server: 12, dfs: null, volume: 'D:', share: '/fs/finance' });
assert.equal(at('server=12').server, null, 'a server is opened from its zone');
assert.equal(at('zone=3&server=12&dfs=4').dfs, null, 'a server and a DFS namespace exclude each other');
assert.equal(at('zone=3&dfs=4').dfs, 4);
assert.equal(at('zone=3&share=/fs/x').share, null, 'a share needs its server');
assert.equal(at('zone=3&server=12&volume=D:%25').volume, null, 'a volume is a drive letter');
assert.equal(at('zone=abc').zone, null);
for (const query of ['', 'zone=3', 'zone=3&server=12', 'zone=3&dfs=4', 'zone=3&server=12&volume=D%3A', 'zone=3&server=12&share=%2Ffs%2Ffinance']) {
  assert.deepEqual(at(new URL(`http://x${topologyHref(at(query))}`).search.slice(1)), at(query), query);
}
assert.equal(topologyHref({}), '/insights/topology');
assert.equal(topologyHref({ server: 12 }), '/insights/topology', 'no server without its zone');

// States: the four of the core, unknown is never an outage
assert.deepEqual(Object.keys(STATE_META).sort(), ['available', 'degraded', 'unavailable', 'unknown']);
assert.equal(STATE_META.unknown.variant, 'muted');

// Capacity: what is known only
assert.equal(capacityLine(null), '');
assert.equal(capacityLine({ quota_limit_bytes: null, measured_bytes: null }), '');
assert.equal(capacityLine({ quota_limit_bytes: 100, quota_used_bytes: 40 }), '40 of 100 (quotas)');
assert.equal(capacityLine({ quota_limit_bytes: 0, quota_used_bytes: 0 }), '0 of 0 (quotas)');
assert.equal(capacityLine({ measured_bytes: 7 }), '7 measured');

console.log('storage-topology: OK');
