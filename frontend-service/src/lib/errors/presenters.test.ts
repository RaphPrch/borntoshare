import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { codeMessage } from './presenters';

// Every message of a business code has its French entry: an error is never shown in English in the French interface
const source = readFileSync(new URL('./presenters.ts', import.meta.url), 'utf8');
const block = source.slice(source.indexOf('const CODE_MESSAGES'), source.indexOf('};', source.indexOf('const CODE_MESSAGES')));
const fr = JSON.parse(readFileSync(new URL('../i18n/locales/fr.json', import.meta.url), 'utf8')) as Record<string, string>;
const sentences = [...block.matchAll(/\bt\('((?:[^'\\]|\\.)+)'/g)].map((m) => m[1].replace(/\\\\/g, '\\'));
const missing = sentences.filter((s) => !(s in fr));
assert.deepEqual(missing, [], `French entries missing: ${missing.join(' | ')}`);

// The codes added by the stabilization have their message
for (const code of ['STORAGE_ENDPOINT_HOST_TAKEN', 'STORAGE_ENDPOINT_DECLARATION_BUSY', 'IDENTITY_SOURCE_DEPENDENCY_CHECK_FAILED']) {
  assert.ok(codeMessage(code), `no message for ${code}`);
}
assert.equal(codeMessage('NOT_A_CODE'), undefined);
console.log(`error messages: ${sentences.length} translated`);
