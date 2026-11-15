import assert from 'node:assert/strict';
import { askPilot } from './pilot-engine';

// The API of the core, simulated: two folders and the permissions of « Finance »
const roots = [
  { storage_root_id: 1, storage_root_name: 'Finance', storage_endpoint_name: 'FILER01', root_path: '\\\\filer01\\DATA\\Finance', password_files: 2, key_files: 0, personal_files: 1,
    quota_used_percent: 92, quota_used_bytes: 9e9, quota_limit_bytes: 1e10, quota_pending_requests: 1, guardians_count: 1, content_size_bytes: 9e9, content_files: 1200, cold_1y_bytes: 6e9 },
  { storage_root_id: 2, storage_root_name: 'TEST', storage_endpoint_name: 'FILER02', root_path: '\\\\filer02\\TEST', guardians_count: 0, content_size_bytes: null }
];
const permissions = {
  storage_root_id: 1, root_path: '', acl_scanned_at: '2026-11-14T10:00:00Z', acl_entries: 4, inheritance: { known: true, broken: false, inherited_entries: 2 },
  snapshot_at: '2026-11-15T07:00:00Z', status: 'ok', summary: { people: 2, read: 1, write: 1, groups: 2, groups_ok: 2, expiring_30d: 1, gaps: 0, accepted_gaps: 0 },
  people: [
    { key: 'a', username: 'cmartin', name: 'Claire Martin', dn: null, level: 'write', via: [{ kind: 'group', group: 'GG_B2S_FINANCE_RW', level: 'write', nested: false }], expires_at: null, revocable_request_ids: [], warnings: [] },
    { key: 'b', username: 'jdupont', name: 'Jean Dupont', dn: null, level: 'read', via: [{ kind: 'request', request_id: 9, code: 'AR-9', level: 'read', group: 'GG_B2S_FINANCE_RX', decided_at: null, expires_at: '2026-12-01', requester: null }], expires_at: '2026-12-01T00:00:00Z', revocable_request_ids: [9], warnings: [] }
  ],
  groups: [{ name: 'GG_B2S_FINANCE_RW', level: 'write', dn: null, ace: 'ok', rights_label: null, inherited_scope: true, members_count: 4 }], system: [], gaps: []
};
const fetchFn = (async (input: RequestInfo | URL) => {
  const url = String(input);
  const body = url.includes('/permissions') ? { data: permissions } : { data: roots };
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
}) as typeof fetch;

const people = await askPilot(fetchFn, 'Exporte-moi tous les utilisateurs du dossier Finance');
assert.equal(people.intent, 'dossier:Finance → personnes');
assert.equal(people.rows.length, 2);
assert.deepEqual(people.columns, ['Personne', 'Login', 'Droit', 'Par', 'Jusqu’au']);
assert.equal(people.rows[1][3].text, 'demande AR-9');
assert.equal(people.file, 'finance_utilisateurs.csv');

const unknown = await askPilot(fetchFn, 'utilisateurs du dossier NOPE');
assert.equal(unknown.ok, false);

const groups = await askPilot(fetchFn, 'Quels groupes donnent accès au dossier Finance ?');
assert.equal(groups.intent, 'dossier:Finance → groupes');
assert.equal(groups.rows[0][0].text, 'GG_B2S_FINANCE_RW');

assert.equal((await askPilot(fetchFn, 'Quels dossiers contiennent des mots de passe ?')).rows.length, 1);
assert.equal((await askPilot(fetchFn, 'Quotas au-delà de 90 %')).intent, 'quota ≥ 90 %');
assert.equal((await askPilot(fetchFn, 'Dossiers jamais mesurés')).rows[0][0].text, 'TEST');
assert.equal((await askPilot(fetchFn, 'Dossiers sans gardien')).rows.length, 1);
assert.equal((await askPilot(fetchFn, 'Dossiers du serveur FILER01')).rows.length, 1);
assert.equal((await askPilot(fetchFn, 'bonjour')).ok, false);
console.log('pilot-engine: ok');
