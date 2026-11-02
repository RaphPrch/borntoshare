import { summarizeZone } from './zone-summary';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

const endpoints = [
  { id: 1, name: 'FILER01', host: '10.0.0.1', endpoint_type: 'smb', operational_state: 'reachable' },
  { id: 2, name: 'OLD', host: '10.0.0.2', endpoint_type: 'smb', operational_state: 'unreachable' },
  { id: 3, name: 'brest', host: 'DFS01', endpoint_type: 'dfs', operational_state: 'unknown' }
];
const roots = [
  { id: 10, name: 'Finance', storage_endpoint_id: 1 },
  { id: 11, name: 'Achats', storage_endpoint_id: 2 },
  { id: 12, name: 'RH', storage_endpoint_id: 1 }
];
const alerts = [
  { storage_root_id: 10, alert_type: 'missing_guardian', severity: 'warning', status: 'open' },
  { storage_root_id: 10, alert_type: 'acl_profile_missing', severity: 'high', status: 'open' },
  { storage_root_id: 11, alert_type: 'root_probe_failed', severity: 'critical', status: 'open' },
  { storage_root_id: 12, alert_type: 'missing_guardian', severity: 'warning', status: 'resolved' }
] as any[];

const zone = summarizeZone(endpoints, roots, alerts);
assert(zone.files.length === 2 && zone.dfs.length === 1, 'DFS namespaces are not file servers');
assert(zone.reachable === 1 && zone.unreachable.map((s) => s.id).join() === '2', 'one server down');
assert(zone.review.map((r) => r.id).join() === '10,11' || zone.review.map((r) => r.id).join() === '11,10', 'only open alerts count');
assert(zone.review.every((r) => r.blocking), 'critical and high alerts block');
assert(zone.noGuardian.map((r) => r.id).join() === '10', 'missing guardians');
assert(zone.reread.map((r) => r.id).join() === '10', 'a folder of an unreachable server is not read again');
assert(zone.servers[0].roots === 2 && zone.servers[0].review === 1, 'counts per server');
assert(summarizeZone(endpoints, roots, alerts, (id) => (id === 2 ? 'checking' : null)).unreachable.length === 0, 'a running test overrides');
console.log('zone-summary OK');
