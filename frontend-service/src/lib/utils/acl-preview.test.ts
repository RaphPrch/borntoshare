import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { RISK_CODES, changeSentence, riskSentence } from './acl-preview';

// Every risk the core names has its sentence
const core = readFileSync(new URL('../../../../core-service/app/services/acl_preview.py', import.meta.url), 'utf8');
const coreCodes = [...core.matchAll(/"code": "([A-Z_]+)"/g)].map((m) => m[1]);
assert.ok(coreCodes.length >= 7, 'risks of the core found');
for (const code of coreCodes) {
  assert.ok(RISK_CODES.includes(code), `no sentence for the risk ${code}`);
  assert.notEqual(riskSentence({ code, values: { names: ['A'], count: 1, days: 9, path: '\\\\fs\\share' } }), code);
}

const base = { target: { principal: 'B2S_FIN_RW', rights: 'modify' as const, scope: 'x' }, read_at: null, current: [], change_from: null, risks: [] };
assert.match(changeSentence({ ...base, change: 'add' }), /B2S_FIN_RW/);
assert.match(changeSentence({ ...base, change: 'level_change', change_from: 'read' }), /B2S_FIN_RW/);
assert.match(riskSentence({ code: 'MANUAL_ENTRIES', values: { count: 7, names: ['a', 'b'] } }), /a, b, …/);

// Every sentence of the file has its French entry
const source = readFileSync(new URL('./acl-preview.ts', import.meta.url), 'utf8');
const fr = JSON.parse(readFileSync(new URL('../i18n/locales/fr.json', import.meta.url), 'utf8')) as Record<string, string>;
const missing = [...source.matchAll(/\bt\('((?:[^'\\]|\\.)+)'/g)].map((m) => m[1]).filter((s) => !(s in fr));
assert.deepEqual(missing, [], `French entries missing: ${missing.join(' | ')}`);
console.log(`acl-preview: ${coreCodes.length} risks described`);
