import { searchIdentityDirectory } from './identityBrowser.api';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

async function testSearchUsesGovernanceSnapshotEndpoint(): Promise<void> {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchFn = async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return new Response(
      JSON.stringify({
        data: {
          items: [
            {
              id: 'CN=Alice,OU=Users,DC=corp,DC=local',
              type: 'user',
              username: 'alice',
              display_name: 'Alice',
              identity_source_id: 7
            }
          ],
          snapshot_id: 44,
          snapshot_status: 'ACTIVE'
        }
      }),
      { status: 200, headers: { 'content-type': 'application/json' } }
    );
  };

  const result = await searchIdentityDirectory(fetchFn, {
    sourceId: 7,
    q: 'alice',
    dn: 'DC=corp,DC=local',
    scope: 'subtree',
    principalType: 'user',
    enabledOnly: true,
    limit: 25
  });

  assert(calls.length === 1, 'one HTTP call expected');
  assert(calls[0].url === '/api/identity/search', 'browser search must use Governance /identity/search');
  assert(calls[0].init.method === 'POST', 'browser search must POST to Governance');

  const body = JSON.parse(String(calls[0].init.body ?? '{}'));
  assert(body.identity_source_id === 7, 'identity_source_id should be forwarded');
  assert(body.query === 'alice', 'query should be forwarded');
  assert(body.dn === 'DC=corp,DC=local', 'dn should be forwarded');
  assert(body.search_scope === 'subtree', 'search scope should be forwarded');
  assert(body.principal_type === 'user', 'principal type should be forwarded');
  assert(body.enabled_only === true, 'enabled_only should be forwarded');

  assert(result.items.length === 1, 'snapshot result should be normalized');
  assert(result.items[0].username === 'alice', 'snapshot user should be returned');
}

async function run(): Promise<void> {
  await testSearchUsesGovernanceSnapshotEndpoint();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
