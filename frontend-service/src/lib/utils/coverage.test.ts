import assert from 'node:assert/strict';
import { coverageRings } from './coverage';

const roots = [
  { storage_root_id: 1, content_size_bytes: 10, guardians_count: 1 },
  { storage_root_id: 2, content_size_bytes: null, guardians_count: 0 },
  { storage_root_id: 3, content_size_bytes: 5, guardians_count: 2 },
  { storage_root_id: 4, estimated_size_bytes: 7, guardians_count: 0 }
];
const by = (rings: ReturnType<typeof coverageRings>) => Object.fromEntries(rings.map((ring) => [ring.key, ring]));

// The counts are those of the lists they open
const all = by(coverageRings({ roots, governance: true, exposure: { governed: 6, total: 10, unknown: 2, open_read: 1, outside: 1 },
  topology: { servers: 4, dfs: 1, states: { available: 3, degraded: 1, unavailable: 0, unknown: 1 } } }));
assert.equal(all.measured.value, 75);
assert.equal(all.guardian.value, 50);
assert.equal(all.governed.value, 75, 'governed out of the folders whose ACL was read');
assert.equal(all.servers.value, 75, 'available out of the servers whose state is known');
assert.equal(all.servers.href, '/insights/topology');

// Still reading: an empty ring, never 0 %
const reading = by(coverageRings({ roots: null, governance: true, exposure: null, topology: null }));
assert.equal(reading.measured.value, null);
assert.equal(reading.governed.value, null);
assert.equal(reading.servers.value, null);

// Not for this person (a guardian: no topology) or without the governance: the ring is not there
assert.deepEqual(Object.keys(by(coverageRings({ roots, governance: true, exposure: null }))), ['measured', 'guardian', 'governed']);
assert.deepEqual(Object.keys(by(coverageRings({ roots, governance: false, exposure: null }))), ['measured']);
console.log('coverage: OK');
