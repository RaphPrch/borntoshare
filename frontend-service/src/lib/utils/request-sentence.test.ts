import assert from 'node:assert/strict';

import { parseRequestSentence, type SentenceRoot } from './request-sentence';

const roots: SentenceRoot[] = [
  { id: 1, name: 'Achats', path: '\\\\172.20.12.195\\PiloteB2Sv3\\Achats', dfsPath: '' },
  { id: 2, name: 'Compta', path: '\\\\172.20.12.195\\PiloteB2Sv3\\Compta', dfsPath: '' },
  { id: 3, name: 'Finance', path: '\\\\172.20.12.195\\PiloteB2S\\Finance', dfsPath: '' },
  { id: 4, name: 'Finance', path: '\\\\172.20.12.195\\PiloteB2Sv2\\Finance', dfsPath: '' },
  { id: 5, name: 'PiloteB2S', path: '\\\\172.20.12.195\\PiloteB2S', dfsPath: '\\\\corp.local\\brest\\Corporate\\Commons\\PiloteB2S' }
];
const now = new Date(2026, 10, 3);

{
  const p = parseRequestSentence('lecture sur Achats et compta pour 30 jours : clôture de novembre', roots, now);
  assert.equal(p.level, 'READ');
  assert.deepEqual(p.rootIds.sort(), [1, 2]);
  assert.deepEqual(p.duration, { days: 30 });
  assert.equal(p.reason, 'clôture de novembre');
}
{
  const p = parseRequestSentence('modification sur \\\\corp.local\\brest\\Corporate\\Commons\\PiloteB2S jusqu’au 31/12 : migration', roots, now);
  assert.equal(p.level, 'WRITE');
  assert.deepEqual(p.rootIds, [5]);
  assert.deepEqual(p.duration, { date: '2026-12-31' });
}
{
  const p = parseRequestSentence("écriture sur Finance jusqu'au 15/01", roots, now);
  assert.equal(p.level, 'WRITE');
  assert.deepEqual(p.rootIds, []);
  assert.deepEqual(p.ambiguous, [{ term: 'finance', ids: [3, 4] }]);
  assert.deepEqual(p.duration, { date: '2027-01-15' });
  assert.equal(p.reason, '');
}
{
  const p = parseRequestSentence('Compta 2 semaines', roots, now);
  assert.equal(p.level, null);
  assert.deepEqual(p.duration, { days: 14 });
  assert.deepEqual(parseRequestSentence('Achats permanent', roots, now).duration, { permanent: true });
  // A name inside another word is not a match
  assert.deepEqual(parseRequestSentence('lecture sur Achatsbis', roots, now).rootIds, []);
}

console.log('request-sentence: ok');
