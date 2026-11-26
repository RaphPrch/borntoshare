import assert from 'node:assert/strict';
import { buildTrends, trendVerdict } from './trends';

const history = [
  { day: '2026-11-24', folders: 100, measured: 80, with_guardian: 90, volume_bytes: 1000, cold_bytes: 400, dup_bytes: 50, secret_folders: 10, open_alerts: 30,
    exposure: { governed: 60, open_read: 20, open_write: 0, outside: 20, unknown: 0 }, servers: null },
  { day: '2026-11-25', folders: 100, measured: 90, with_guardian: 90, volume_bytes: 1100, cold_bytes: 380, dup_bytes: 50, secret_folders: 12, open_alerts: 25,
    exposure: null, servers: { available: 3, degraded: 1, unavailable: 0, unknown: 2 } },
  { day: '2026-11-26', folders: 100, measured: 95, with_guardian: 90, volume_bytes: 1200, cold_bytes: 350, dup_bytes: 50, secret_folders: 8, open_alerts: 20,
    exposure: { governed: 75, open_read: 15, open_write: 0, outside: 10, unknown: 5 }, servers: { available: 4, degraded: 0, unavailable: 0, unknown: 2 } }
];
const by = Object.fromEntries(buildTrends(history).map((trend) => [trend.key, trend]));

assert.deepEqual(by.measured.points, [80, 90, 95]);
assert.equal(by.measured.delta, 15);
assert.equal(trendVerdict(by.measured), 'better');
// A day where the exposure was not read is a gap, not 0 %; unknown folders are left out of the share
assert.deepEqual(by.governed.points, [60, 75]);
// Servers: available out of those whose state is known
assert.deepEqual(by.servers.points, [75, 100]);
// A size that grows is worse; cold data that shrinks is better; steady stays steady
assert.equal(trendVerdict(by.volume), 'worse');
assert.equal(trendVerdict(by.cold), 'better');
assert.equal(trendVerdict(by.dups), 'steady');
assert.equal(trendVerdict(by.guardian), 'steady');
// One day only: no change to tell
const single = buildTrends(history.slice(0, 1));
assert.ok(single.every((trend) => trend.delta == null && trendVerdict(trend) == null));
assert.ok(buildTrends([]).every((trend) => trend.last == null));
console.log('trends: OK');
