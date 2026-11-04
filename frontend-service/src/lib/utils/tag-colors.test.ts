import assert from 'node:assert/strict';

import { familyShades, nameClash } from './tag-colors';

assert.deepEqual(familyShades('Sensibilité'), familyShades('sensibilite'));
assert.equal(familyShades('').length, 4);
assert.notDeepEqual(familyShades(''), familyShades('Département'));

const tags = ['Finance', 'RH', 'Données personnelles'];
assert.deepEqual(nameClash('finance', tags), { kind: 'same', name: 'Finance' });
assert.deepEqual(nameClash('Finances', tags), { kind: 'near', name: 'Finance' });
assert.deepEqual(nameClash('Donnees personnelles', tags), { kind: 'same', name: 'Données personnelles' });
assert.equal(nameClash('Juridique', tags), null);
assert.equal(nameClash('RHX', tags), null); // too short to be « near »
assert.equal(nameClash('', tags), null);

console.log('tag-colors: ok');
