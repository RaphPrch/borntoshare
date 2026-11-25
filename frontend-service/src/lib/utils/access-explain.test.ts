import assert from 'node:assert/strict';
import { LIMITS, explainGrant, grantChain, type Grant } from './access-explain';

const base = { principal: 'CORP\\GG_Finance_Write', rights: 'modify', deny: false, inherited: false } as const;

// Through a group: the sentence names the group and the right
const group: Grant = { ...base, kind: 'group', group: 'GG_Finance_Write', via: ['GG_Finance_Write'] };
const [sentence] = explainGrant('Paul Martin', group, 'Finance');
assert.match(sentence.key, /because they belong to the group \{group\}/);
assert.equal(sentence.vars.group, 'GG_Finance_Write');
assert.equal(sentence.vars.right, 'Modify');

// Nested: the first group and the chain up to the one holding the entry
const nested: Grant = { ...base, kind: 'nested', group: 'GL_Finance', via: ['GG_Compta', 'GG_Finance_Write', 'GL_Finance'] };
const [nestedSentence] = explainGrant('Paul Martin', nested, 'Finance');
assert.equal(nestedSentence.vars.first, 'GG_Compta');
assert.equal(nestedSentence.vars.chain, 'GG_Finance_Write › GL_Finance');
assert.deepEqual(grantChain('Paul Martin', nested), ['Paul Martin', 'GG_Compta', 'GG_Finance_Write', 'GL_Finance']);

// Direct entry, inherited: two sentences
const direct = explainGrant('Paul Martin', { ...base, kind: 'direct', principal: 'CORP\\paul', inherited: true }, 'Archives');
assert.equal(direct.length, 2);
assert.match(direct[0].key, /their own account/);
assert.equal(direct[1].key, 'The entry is inherited from a parent folder.');
assert.deepEqual(grantChain('Paul Martin', { ...base, kind: 'direct', principal: 'CORP\\paul' }), ['Paul Martin', 'CORP\\paul']);

// A deny is said as a deny, whatever the way in
const [denied] = explainGrant('Paul Martin', { ...group, deny: true }, 'Finance');
assert.match(denied.key, /is denied/);

// The whole company
const [broad] = explainGrant('Paul Martin', { ...base, kind: 'broad', principal: 'Everyone', rights: 'read' }, 'Public');
assert.match(broad.key, /covers every account/);
assert.equal(broad.vars.right, 'Read');

// Group mode: a group reaching a folder through the group holding it
const parent: Grant = { ...base, kind: 'parent', group: 'GL_Finance', via: ['GG_Compta', 'GL_Finance'] };
assert.equal(explainGrant('GG_Compta', parent, 'Finance')[0].vars.chain, 'GL_Finance');
assert.deepEqual(grantChain('GG_Compta', parent), ['GG_Compta', 'GL_Finance']);

// Every limit sent by the core has its sentence; the SMB one never claims a complete access
for (const code of ['ntfs_only', 'subfolders_not_read', 'local_groups_not_resolved', 'deny_present', 'account_state_unknown',
  'no_directory_snapshot', 'group_depth_truncated', 'acl_not_read', 'people_truncated']) {
  assert.ok(LIMITS[code], code);
}
assert.match(LIMITS.ntfs_only, /SMB/);

console.log('access-explain: OK');
