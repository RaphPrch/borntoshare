import assert from 'node:assert/strict';
import {
  buildServiceAccountsPayload,
  domainFromBaseDn,
  draftsForCapabilities,
  emptyServiceAccountDrafts,
  serviceAccountDraftError,
  serviceAccountDraftsFrom
} from './service-accounts';

assert.equal(domainFromBaseDn('DC=Example,DC=Test'), 'example.test');
assert.equal(domainFromBaseDn('OU=Users, DC=example, DC=test'), 'example.test');
assert.equal(domainFromBaseDn(''), '');

// Listed accounts (has_password) and internal metadata (bind_password_ref) give the same drafts
const listed = serviceAccountDraftsFrom({ snapshot: { bind_dn: 'svc-read', has_password: true } });
const internal = serviceAccountDraftsFrom({ snapshot: { bind_dn: 'svc-read', bind_password_ref: 'sm://x' } });
assert.deepEqual(listed, internal);
assert.equal(listed.snapshot.dedicated, true);
assert.equal(listed.auth.dedicated, false);

// A new dedicated account needs a password; a stored one can stay unchanged
const drafts = emptyServiceAccountDrafts();
drafts.auth = { dedicated: true, bind_dn: 'svc-auth', password: '', has_password: false };
assert.equal(serviceAccountDraftError(drafts), 'auth');
drafts.auth.has_password = true;
assert.equal(serviceAccountDraftError(drafts), null);

// A disabled capability drops its dedicated account
const scoped = draftsForCapabilities(drafts, { auth: false, snapshot_enabled: true });
assert.equal(scoped.auth.dedicated, false);

async function payload(): Promise<void> {
  const stored: unknown[] = [];
  const fetchFn = (async (_url: string, init?: RequestInit) => {
    stored.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ bind_password_ref: 'sm://identity-sources/prov' }), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    });
  }) as typeof fetch;

  const input = emptyServiceAccountDrafts();
  input.auth = { dedicated: true, bind_dn: 'svc-auth', password: '', has_password: true };
  input.provisioning = { dedicated: true, bind_dn: 'svc-prov', password: 'secret', has_password: false };

  const accounts = await buildServiceAccountsPayload(fetchFn, input, 'identity-source/ldaps/dc01');

  assert.equal(accounts.snapshot, null);
  assert.deepEqual(accounts.auth, { bind_dn: 'svc-auth' });
  assert.deepEqual(accounts.provisioning, { bind_dn: 'svc-prov', bind_password_ref: 'sm://identity-sources/prov' });
  // One secret per purpose, so the dedicated password never overwrites the main one
  assert.equal(stored.length, 1);
  assert.equal((stored[0] as { name: string }).name, 'identity-source/ldaps/dc01/provisioning');
}

payload().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
