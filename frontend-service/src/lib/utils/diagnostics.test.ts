import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { describeCheck, knownChecks, sortChecks } from './diagnostics';
import type { DiagnosticCheck } from '$lib/api/infrastructure';

const check = (code: string, result: DiagnosticCheck['result'], severity: DiagnosticCheck['severity'], values = {}): DiagnosticCheck => ({
  code, area: 'x', result, severity, values
});

// Every check the core runs has its sentences (the list of app/services/diagnostics.py)
const core = readFileSync(new URL('../../../../core-service/app/services/diagnostics.py', import.meta.url), 'utf8');
const coreCodes = new Set([...core.matchAll(/"((?:config|secrets|database|queue|disk|jobs|workers|health|module)\.[a-z_]+)"/g)].map((m) => m[1]));
for (const group of ['directories', 'group_ous', 'file_servers', 'sso']) coreCodes.add(`components.${group}`);
for (const code of coreCodes) assert.ok(knownChecks().includes(code), `no sentence for the check ${code}`);

// A problem gives its explanation with the values, and what to do; an ok check gives no action
const down = describeCheck(check('components.file_servers', 'warning', 'medium', { total: 3, down: 2, names: ['FS1', 'FS2'] }));
assert.match(down.detail, /2/);
assert.match(down.detail, /FS1, FS2/);
assert.ok(down.action);
assert.match(describeCheck(check('components.file_servers', 'error', 'medium', { total: 43, down: 43, names: ['FS1'] })).detail, /FS1, …/);
assert.equal(describeCheck(check('disk.space', 'ok', 'info', { percent: 40, free_gb: 60, total_gb: 100 })).action, null);
assert.equal(describeCheck(check('jobs.queue', 'unknown', 'high')).action, null);
assert.equal(describeCheck(check('not.known', 'error', 'high')).title, 'not.known');

// Problems first, the most severe at the top
const sorted = sortChecks([check('a', 'ok', 'info'), check('b', 'warning', 'medium'), check('c', 'error', 'medium'), check('d', 'error', 'critical')]);
assert.deepEqual(sorted.map((c) => c.code), ['d', 'c', 'b', 'a']);

// Every sentence of this file has its French entry
const source = readFileSync(new URL('./diagnostics.ts', import.meta.url), 'utf8');
const fr = JSON.parse(readFileSync(new URL('../i18n/locales/fr.json', import.meta.url), 'utf8')) as Record<string, string>;
const sentences = [...source.matchAll(/\bt\('((?:[^'\\]|\\.)+)'/g)].map((m) => m[1].replace(/\\'/g, "'"));
const missing = sentences.filter((s) => !(s in fr));
assert.deepEqual(missing, [], `French entries missing: ${missing.join(' | ')}`);

console.log(`diagnostics: ${coreCodes.size} checks of the core described, ${sentences.length} sentences translated`);
