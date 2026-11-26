/**
 * Access Explorer: the sentence that explains one way an account or a group reaches a folder, and the limits of what
 * is known. Pure: it returns the sentence keys and their values, the page translates them (t) — and the tests read them.
 */

export type Grant = {
  kind: 'direct' | 'group' | 'nested' | 'parent' | 'broad';
  principal: string;
  rights: 'full' | 'modify' | 'read' | 'special';
  deny: boolean;
  inherited: boolean;
  group?: string | null;
  via?: string[];
};
export type Sentence = { key: string; vars: Record<string, string> };

export const RIGHTS_LABEL: Record<string, string> = { full: 'Full control', modify: 'Modify', read: 'Read', special: 'Special rights' };

/** One way in, said plainly: who, which right, through what, and whether a deny or an inheritance is involved. */
export function explainGrant(who: string, grant: Grant, folder: string): Sentence[] {
  const right = RIGHTS_LABEL[grant.rights] ?? grant.rights;
  const via = grant.via ?? [];
  const vars: Record<string, string> = { who, right, folder, principal: grant.principal, group: grant.group ?? grant.principal };
  const out: Sentence[] = [];
  if (grant.deny) {
    out.push({ key: '{who} is denied {right} on {folder} by an entry given to {principal}: a deny wins over the allows.', vars });
  } else if (grant.kind === 'direct') {
    out.push({ key: '{who} has {right} on {folder} through an entry given to their own account.', vars });
  } else if (grant.kind === 'group') {
    out.push({ key: '{who} has {right} on {folder} because they belong to the group {group}, which holds a {right} entry.', vars });
  } else if (grant.kind === 'nested') {
    out.push({
      key: '{who} has {right} on {folder} because they belong to {first}, member of {chain}, which holds a {right} entry.',
      vars: { ...vars, first: via[0] ?? vars.group, chain: via.slice(1).join(' › ') || vars.group }
    });
  } else if (grant.kind === 'parent') {
    out.push({
      key: '{who} gives {right} on {folder} because it is a member of {chain}, which holds a {right} entry.',
      vars: { ...vars, chain: via.slice(1).join(' › ') || vars.group }
    });
  } else {
    out.push({ key: '{who} has {right} on {folder} because the entry is given to {principal}, which covers every account of the domain.', vars });
  }
  if (grant.inherited) out.push({ key: 'The entry is inherited from a parent folder.', vars: {} });
  return out;
}

/** The full chain, for the path drawn under the sentence: the account, its groups in order, the entry, the folder. */
export function grantChain(who: string, grant: Grant): string[] {
  if (grant.kind === 'direct' || grant.kind === 'broad') return [who, grant.principal];
  if (grant.kind === 'parent') return [...(grant.via ?? [who])];
  return [who, ...(grant.via?.length ? grant.via : [grant.group ?? grant.principal])];
}

/** What the computation does not know, in the words of the page (codes sent by core-service). */
export const LIMITS: Record<string, string> = {
  ntfs_only: 'NTFS rights only: the share permissions (SMB) and the network rules are not read. The effective access can be narrower.',
  subfolders_not_read: 'Rights read on the governed folder: a sub-folder may break the inheritance.',
  local_groups_not_resolved: 'The local groups of the server (Administrators, Users…) are not resolved to people.',
  deny_present: 'A deny entry is present: the effective right may be lower than shown.',
  account_state_unknown: 'The account state (enabled or disabled) is known after the next reading of the directory.',
  no_directory_snapshot: 'No reading of the directory: the groups and their members are not known.',
  group_depth_truncated: 'Nested groups beyond 10 levels are not followed.'
};
