import { normalizePrincipalList } from './principal-search';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testIdentityIdPreservedFromDirectField(): void {
  const rows = normalizePrincipalList([
    {
      id: 'CN=John,OU=Users,DC=corp,DC=local',
      identity_id: 123,
      username: 'john.doe',
      type: 'user'
    }
  ]);

  assert(rows.length === 1, 'one row should be normalized');
  assert(rows[0].identity_id === 123, 'identity_id should be preserved from direct field');
}

function testIdentityIdPreservedFromNestedIdentity(): void {
  const rows = normalizePrincipalList([
    {
      id: 'CN=Alice,OU=Users,DC=corp,DC=local',
      identity: { identity_id: 456 },
      username: 'alice',
      type: 'user'
    }
  ]);

  assert(rows.length === 1, 'one row should be normalized');
  assert(rows[0].identity_id === 456, 'identity_id should be preserved from nested identity field');
}

function testStableIdFallbackWhenIdMissing(): void {
  const rows = normalizePrincipalList([
    {
      identity_id: 789,
      external_id: 'S-1-5-21-789',
      username: 'fallback-user',
      type: 'user'
    }
  ]);

  assert(rows.length === 1, 'row should not be dropped when id is missing but identity tokens exist');
  assert(String(rows[0].id) === 'S-1-5-21-789', 'stable id should fallback to external_id');
  assert(rows[0].identity_id === 789, 'identity_id should still be preserved');
}

function testDoesNotUnwrapEnvelopeDataContract(): void {
  const rows = normalizePrincipalList({
    data: {
      items: [
        {
          id: 'CN=Wrapped,OU=Users,DC=corp,DC=local',
          username: 'wrapped.user',
          type: 'user'
        }
      ]
    }
  });

  assert(rows.length === 0, 'wrapped payloads must not be treated as valid browse payloads');
}

async function run(): Promise<void> {
  testIdentityIdPreservedFromDirectField();
  testIdentityIdPreservedFromNestedIdentity();
  testStableIdFallbackWhenIdMissing();
  testDoesNotUnwrapEnvelopeDataContract();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
