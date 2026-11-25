import assert from 'node:assert/strict';
import { applyPilotAction, askPilot, pilotExamples } from './pilot-engine';

// The API of the core, simulated: two folders and the permissions of « Finance »
const roots = [
  { storage_root_id: 1, storage_root_name: 'Finance', storage_endpoint_name: 'FILER01', root_path: '\\\\filer01\\DATA\\Finance', password_files: 2, key_files: 0, personal_files: 1,
    quota_used_percent: 92, quota_used_bytes: 9e9, quota_limit_bytes: 1e10, quota_pending_requests: 1, guardians_count: 1, guardians: [{ identity_id: 5, login: 'amartin', name: 'Alice Martin' }], content_size_bytes: 9e9, content_files: 1200, cold_1y_bytes: 6e9, tags: [{ id: 7, name: 'Archive' }] },
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
const searched: string[] = [];
const posted: Array<{ url: string; body: any }> = [];
const tags = [{ id: 7, name: 'Archive' }, { id: 8, name: 'Données de santé' }, { id: 9, name: 'Confidentiel', family: 'Confidentialité' }];
const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  if (init?.method === 'POST') {
    const sent = JSON.parse(String(init.body));
    posted.push({ url, body: sent });
    const data = url.includes('/bulk-tags') ? { updated: sent.root_ids, failed: [] } : { ok: true };
    return new Response(JSON.stringify({ data }), { status: 200, headers: { 'content-type': 'application/json' } });
  }
  const day = 86_400_000;
  const body = url.includes('/access-reviews') ? { data: [{ id: 3, name: 'Revue T4', status: 'open', total: 10, decided: 4, folders: 2, due_at: '2020-01-01T00:00:00Z' }, { id: 2, name: 'Revue T3', status: 'closed', total: 5, decided: 5, folders: 1 }] }
    : url.includes('/access-requests') ? { data: [
        { request_id: 41, request_code: 'AR-41', status: 'pending', overdue: true, created_at: '2026-01-01T00:00:00Z', due_at: '2026-01-04T00:00:00Z', storage_root_name: 'Finance', requested_for_display: 'Jean Dupont', permission: 'READ' },
        { request_id: 42, request_code: 'AR-42', status: 'pending', overdue: false, storage_root_name: 'TEST', requested_for_display: 'Ana Lee' },
        { request_id: 43, request_code: 'AR-43', status: 'approved', expires_at: new Date(Date.now() + 3 * day).toISOString(), storage_root_name: 'Finance', requested_for_display: 'Claire Martin', access_profile_name: 'write' },
        { request_id: 44, request_code: 'AR-44', status: 'approved', expires_at: new Date(Date.now() + 20 * day).toISOString(), storage_root_name: 'TEST', requested_for_display: 'Bob' }] }
    : /\/tags(\?|$)/.test(url) ? { data: tags }
    : url.includes('/permissions') ? { data: permissions }
    : url.includes('/modules/fives/files/search') ? { data: { files: [{ storage_root_id: 1, folder_name: 'Finance', path: 'Finance\\Bilan.pdf', size: 2e8, modified: null, owner: 'CORP\\jane' }], total: 1, bytes: 2e8 }, search: url }
    : url.includes('/rights-review') ? { data: { folders: [{ path: 'Finance\\RH', codes: ['ORPHAN_SID', 'EXPLICIT_ENTRY'] }, { path: 'Finance\\Paie', codes: ['INHERITANCE_BROKEN'] }] } }
    : url.includes('/sensitivity') ? { data: { findings: [{ path: 'Finance\\mdp.txt', category: 'password', acl: { broad: true, by: ['CORP\\Utilisateurs du domaine'] } },
        { path: 'Finance\\cle.pem', category: 'key', acl: { broad: false } }] } }
    : { data: roots };
  if (url.includes('/modules/fives/files/search')) searched.push(url);
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


// ---- 5S module: files, sensitive files open to all, rights to review ----
const files = await askPilot(fetchFn, 'Fichiers pdf de plus de 100 Mo du propriétaire CORP\\jane');
assert.equal(files.rows.length, 1);
assert.ok(searched[0].includes('ext=pdf') && searched[0].includes('min_bytes=104857600') && searched[0].includes('owner=CORP'));
const open = await askPilot(fetchFn, 'Fichiers sensibles ouverts à tous');
assert.equal(open.rows.length, 1);
assert.equal(open.rows[0][1].text, 'Finance\\mdp.txt');
const orphans = await askPilot(fetchFn, 'Dossiers avec un SID orphelin');
assert.equal(orphans.intent, 'dossiers → SID orphelins');
assert.equal(orphans.rows.length, 1);
assert.equal((await askPilot(fetchFn, 'Dossiers avec des droits à revoir')).rows.length, 2);


// ---- actions: tags put or taken off, planned first, applied on demand ----
const add = await askPilot(fetchFn, 'Ajoute le tag Données de santé aux dossiers Finance et TEST');
assert.deepEqual(add.action, { kind: 'tag-add', tagId: 8, tagName: 'Données de santé', rootIds: [1, 2] });
assert.equal(posted.length, 0, 'nothing is changed before « Appliquer »');
assert.deepEqual(await applyPilotAction(fetchFn, add.action!), { done: 2, failed: [] });
assert.deepEqual(posted[0].body, { root_ids: [1, 2], tag_ids: [8] });
const already = await askPilot(fetchFn, 'ajoute le tag Archive au dossier Finance');
assert.equal(already.action, undefined);
assert.equal(already.ok, false);
const remove = await askPilot(fetchFn, 'Retire le tag Archive des dossiers du serveur FILER');
assert.deepEqual(remove.action?.rootIds, [1]);
await applyPilotAction(fetchFn, remove.action!);
assert.deepEqual(posted[1].body, { tag_id: 7, resource_type: 'storage_root', resource_id: 1 });
const sansGardien = await askPilot(fetchFn, 'Pose le tag « Confidentiel » sur les dossiers sans gardien');
assert.deepEqual(sansGardien.action?.rootIds, [2]);
const missingTag = await askPilot(fetchFn, 'Ajoute le tag Secret défense au dossier Finance');
assert.equal(missingTag.ok, false);
assert.ok(missingTag.text.includes('Archive'));
const missingFolder = await askPilot(fetchFn, 'Ajoute le tag Confidentiel aux dossiers Finance et NOPE');
assert.deepEqual(missingFolder.action?.rootIds, [1]);
assert.ok(missingFolder.text.includes('Introuvable : nope'));
console.log('pilot-engine actions: ok');


// ---- Assistant: people × folders ----
const responsible = await askPilot(fetchFn, 'Exporte-moi la liste de tous les utilisateurs avec le nombre de données dont ils sont responsables');
assert.equal(responsible.intent, 'gardiens → dossiers, volume');
assert.deepEqual(responsible.columns, ['Login', 'Nom', 'Dossiers', 'Volume', 'Dossiers sensibles']);
assert.equal(responsible.rows.length, 1);
assert.deepEqual([0, 1, 2, 4].map((column) => responsible.rows[0][column].text), ['amartin', 'Alice Martin', '1', '1']);
assert.notEqual(responsible.rows[0][3].text, '—', 'the volume of the guarded folders');
const guardiansSensitive = await askPilot(fetchFn, 'Exporte-moi la liste des gardiens dont leurs données sont sensibles');
assert.equal(guardiansSensitive.intent, 'gardiens × dossiers sensibles');
assert.equal(guardiansSensitive.rows.length, 1);
assert.equal(guardiansSensitive.rows[0][2].text, 'Finance');
assert.ok(guardiansSensitive.rows[0][3].text.includes('Mots de passe') && guardiansSensitive.rows[0][3].text.includes('Données personnelles'));
const reachSensitive = await askPilot(fetchFn, 'Exporte-moi la liste des utilisateurs qui accèdent à de la donnée sensible');
assert.equal(reachSensitive.intent, 'personnes × dossiers sensibles');
assert.deepEqual(reachSensitive.columns, ['Login', 'Nom', 'Droit', 'Dossier', 'Sensibilité']);
assert.deepEqual(reachSensitive.rows.map((row) => [row[0].text, row[2].text, row[3].text]), [['cmartin', 'Modification', 'Finance'], ['jdupont', 'Lecture', 'Finance']]);
assert.equal(reachSensitive.file, 'acces_donnees_sensibles.csv');
// A plain folder question is still a folder question
assert.equal((await askPilot(fetchFn, 'Exporte-moi tous les utilisateurs du dossier Finance')).intent, 'dossier:Finance → personnes');

// ---- 5S module off: its questions are not answered, its examples not offered ----
const off = { fives: false };
const duplicates = await askPilot(fetchFn, 'Doublons à libérer', off);
assert.equal(duplicates.ok, false);
assert.equal(duplicates.intent, 'module 5S');
assert.equal((await askPilot(fetchFn, 'Fichiers pdf de plus de 100 Mo', off)).intent, 'module 5S');
assert.equal((await askPilot(fetchFn, 'Dossiers avec des droits à revoir', off)).intent, 'module 5S');
assert.equal((await askPilot(fetchFn, 'Fichiers sensibles ouverts à tous', off)).rows.length, 1, 'the sensitivity scan is not the 5S');
assert.ok((await askPilot(fetchFn, 'Retire le tag Archive des dossiers du serveur FILER', off)).action, 'a tag named Archive is not a 5S question');
assert.ok(!pilotExamples(false).includes('Doublons à libérer') && pilotExamples(true).includes('Doublons à libérer'));
console.log('assistant: ok');

// Access governance: requests past their deadline, accesses that end soon, open reviews
{
  const late = await askPilot(fetchFn, 'Demandes en retard');
  assert.equal(late.intent, 'demandes → en retard');
  assert.deepEqual(late.rows.map((row) => row[0].text), ['AR-41']);
  assert.equal(late.rows[0][4].tone, 'bad');
  const week = await askPilot(fetchFn, 'Accès qui expirent cette semaine');
  assert.deepEqual(week.rows.map((row) => row[0].text), ['Claire Martin']);
  assert.equal(week.rows[0][2].text, 'Modification');
  const month = await askPilot(fetchFn, 'Accès qui expirent ce mois');
  assert.equal(month.rows.length, 2);
  const reviews = await askPilot(fetchFn, 'Revues d’accès à traiter');
  assert.deepEqual(reviews.rows.map((row) => row[0].text), ['Revue T4']);
  assert.equal(reviews.rows[0][1].text, '6');
  assert.ok(pilotExamples(false).includes('Demandes en retard'));
}
