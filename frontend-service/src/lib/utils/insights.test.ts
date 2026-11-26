import assert from 'node:assert/strict';
import { foldersMatching } from '../components/storage-roots/folder-query';
import { buildInsights } from './insights';

// The folders of the build's real cases: a figure must equal the list its « See » opens
const rows = [
  { storage_root_id: 1, content_size_bytes: 100, cold_1y_bytes: 80, password_files: 0, key_files: 2, guardians_count: 0, quota_used_percent: 80, quota_warn_percent: 75 },
  { storage_root_id: 2, content_size_bytes: 100, cold_1y_bytes: 10, password_files: 3, key_files: 0, guardians_count: 1, quota_used_percent: 86, quota_warn_percent: 90, quota_pending_requests: 1 },
  { storage_root_id: 3, content_size_bytes: null, estimated_size_bytes: null, measure_status: 'failed', guardians_count: 2, inheritance_broken: true, junk_files: 4 },
  { storage_root_id: 4, content_size_bytes: null, measure_status: 'running', dup_wasted_bytes: 5, remediation_status: 'overdue', guardians_count: 1 }
];

const insights = buildInsights(rows, { governance: true, fives: true });
for (const insight of insights) {
  assert.equal(insight.count, foldersMatching(rows, insight.query).length, `${insight.key}: the figure is the list of ${insight.query}`);
}
const byKey = Object.fromEntries(insights.map((insight) => [insight.key, insight]));
// Passwords or keys: folder 1 (keys only) counts, as the list est:secret shows
assert.equal(byKey.secrets.count, 2);
assert.equal(byKey.secrets.big, '5');
// Quota: the folder's own threshold (folder 1 at 80 % of 75 %), not a fixed 85 % (folder 2 at 86 % of 90 %)
assert.equal(byKey.quota.count, 1);
// Never measured: no size, whatever the measure state (the list est:non-mesure)
assert.equal(byKey.never.count, 2);
// Without the governance: no guardian nor inheritance recommendation
assert.ok(!buildInsights(rows, { governance: false, fives: true }).some((insight) => insight.license === 'governance'));
// Without the 5S module: nothing of its measures nor of its sensitivity scan
const without5S = buildInsights(rows, { governance: true, fives: false });
assert.ok(without5S.every((insight) => insight.license !== 'fives'));
assert.ok(!without5S.some((insight) => ['cold', 'dups', 'junk', 'secrets', 'corrections'].includes(insight.key)));
// The most pressing first
const tones = insights.map((insight) => insight.tone);
assert.deepEqual(tones, [...tones].sort((a, b) => ['bad', 'warn', 'mut', 'ok'].indexOf(a) - ['bad', 'warn', 'mut', 'ok'].indexOf(b)));

console.log('insights: OK');
