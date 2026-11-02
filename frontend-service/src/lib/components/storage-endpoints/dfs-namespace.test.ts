import { dfsCounts, dfsReadAge, dfsReadIsStale, type DfsInfo } from './dfs-namespace';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

const target = (server: string, id: number | null) => ({ unc: `\\\\${server}\\s`, server, storage_endpoint_id: id, storage_endpoint_name: id ? server : null, storage_root_id: null });
const info: DfsInfo = {
  path: '\\\\corp.local\\brest',
  type: 'domain',
  root_targets: ['\\\\DFS01\\brest'],
  read_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
  error: null,
  links: [
    { path: 'A', dfs_path: '', targets: [target('FILER01', 1)], state: 'managed' },
    { path: 'B', dfs_path: '', targets: [target('FILER01', 1), target('filer02', null)], state: 'unknown_server' },
    { path: 'C', dfs_path: '', targets: [target('FILER01', 1)], state: 'to_manage' },
    { path: 'D', dfs_path: '', targets: [target('FILER01', 1)], state: 'partial' },
    { path: 'E', dfs_path: '', targets: [], state: 'no_target' }
  ]
};
const counts = dfsCounts(info);
assert(counts.all === 5 && counts.managed === 1 && counts.todo === 2 && counts.unknown === 1 && counts.noTarget === 1, 'states');
assert(counts.servers === 2 && counts.unknownServers.join() === 'FILER02', 'target servers');
assert(dfsReadAge(info) === 2 && !dfsReadIsStale(info), 'read 2 days ago');
assert(dfsReadIsStale({ ...info, read_at: null }), 'never read is stale');
assert(dfsCounts(null).all === 0, 'nothing read');
console.log('dfs-namespace OK');
