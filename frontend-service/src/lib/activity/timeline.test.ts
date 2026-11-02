import { activitySummary, categoryOf, changedValues, groupByDay } from './timeline';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

const now = Date.parse('2026-11-02T14:00:00Z');
const at = (days: number) => new Date(now - days * 86_400_000).toISOString();
const items = [
  { action: 'access_request.approved', outcome: 'success', created_at: at(1) },
  { action: 'access_request.revoked', outcome: 'success', created_at: at(2) },
  { action: 'storage_root.inheritance_broken', outcome: 'success', created_at: at(3) },
  { action: 'storage_root.probe_result_recorded', outcome: 'failed', created_at: at(0) },
  { action: 'storage_endpoint.dfs_read', outcome: 'success', created_at: at(0) },
  { action: 'tag.attached', outcome: 'success', created_at: at(40) }
];
assert(categoryOf(items[0]) === 'access' && categoryOf(items[2]) === 'config', 'access and configuration');
assert(categoryOf(items[3]) === 'failure' && categoryOf(items[4]) === 'check', 'failure first, then checks');
const sum = activitySummary(items, now);
assert(sum.granted === 1 && sum.revoked === 1 && sum.config === 1 && sum.failures === 1, `summary ${JSON.stringify(sum)}`);
const days = groupByDay(items.map((entry) => ({ entry, ms: Date.parse(entry.created_at) })));
assert(days[0].rows.length === 2 && days.length === 5, 'grouped by day, newest first');
const changes = changedValues({ context_json: { before: { name: 'A', bind_password_ref: 'x', zone: 1 }, after: { name: 'B', bind_password_ref: 'y', zone: 1 } } });
assert(changes.length === 1 && changes[0].key === 'name' && changes[0].after === 'B', 'only real changes, never secrets');
console.log('timeline OK');
