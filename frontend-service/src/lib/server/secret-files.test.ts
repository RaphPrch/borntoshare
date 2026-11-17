import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { forgetServerSecrets, serverSecret } from './secret-files';

const env = process.env as Record<string, string | undefined>;
const folder = mkdtempSync(join(tmpdir(), 'b2s-secret-'));
const file = join(folder, 'b2s_internal_token');
writeFileSync(file, 'from-the-file\n', { mode: 0o600 });

// The file of the podman secret (NAME_FILE): read, trimmed, kept
delete env.INTERNAL_TOKEN;
env.INTERNAL_TOKEN_FILE = file;
assert.equal(serverSecret('INTERNAL_TOKEN'), 'from-the-file');
writeFileSync(file, 'changed', { mode: 0o600 });
assert.equal(serverSecret('INTERNAL_TOKEN'), 'from-the-file', 'read once: a rotation restarts the service');

// A value in the environment (development) comes first
forgetServerSecrets();
env.INTERNAL_TOKEN = 'from-env';
assert.equal(serverSecret('INTERNAL_TOKEN'), 'from-env');

// Neither: empty (the caller decides; the principal key refuses to start in production)
forgetServerSecrets();
delete env.INTERNAL_TOKEN;
delete env.INTERNAL_TOKEN_FILE;
assert.equal(serverSecret('INTERNAL_TOKEN'), '');
console.log('secret-files: ok');
