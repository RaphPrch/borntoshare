import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';

import { signActorAssertion } from './principal-cookie';

// The format core-service checks (app/core/service_identity.py): base64url(JSON).base64url(HMAC-SHA256(body))
const key = 'k'.repeat(48);
const assertion = await signActorAssertion({ id: 42, roles: ['Platform_Admin', ' guardian ', 'guardian'], name: 'Alice' }, key, 1_000_000);
const [body, signature] = assertion.split('.');
const expected = createHmac('sha256', key).update(body).digest('base64url');
assert.equal(signature, expected, 'HMAC-SHA256 of the body, base64url without padding');

const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
assert.deepEqual(payload, { id: 42, roles: ['guardian', 'platform_admin'], name: 'Alice', aud: 'core', exp: 1_000_060 });

// Another key gives another signature: nobody without the key forges one
const other = await signActorAssertion({ id: 42, roles: ['platform_admin'], name: null }, 'x'.repeat(48), 1_000_000);
assert.notEqual(other.split('.')[1], createHmac('sha256', key).update(other.split('.')[0]).digest('base64url'));
console.log('actor assertion: format of core-service');
