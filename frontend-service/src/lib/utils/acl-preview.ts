// Sentences of the dry run of an approval on the NTFS permissions (ApprovalPlan): what changes, what is there, the risks.
import { t } from '$lib/i18n';
import type { AclPreview, AclRights } from '$lib/api/access-requests';

export function rightsLabel(rights: AclRights | 'read' | 'modify' | null | undefined): string {
  return { full: t('Full control'), modify: t('Modify'), read: t('Read and execute'), special: t('Special permissions'), deny: t('Deny') }[rights ?? 'special'] ?? String(rights);
}

export function kindLabel(kind: AclPreview['current'][number]['kind']): string {
  return { managed: t('Managed by BornToShare'), system: t('System'), broad: t('Whole company'), other: t('Set by hand') }[kind];
}

export function changeSentence(preview: AclPreview): string {
  const group = preview.target.principal ?? '—';
  if (preview.change === 'add') return t('Entry added: {group}, {rights}, on this folder, its subfolders and files.', { group, rights: rightsLabel(preview.target.rights) });
  if (preview.change === 'present') return t('{group} already has this access in the ACL: nothing is written.', { group });
  if (preview.change === 'level_change')
    return t('{group} goes from {from} to {to}.', { group, from: rightsLabel(preview.change_from), to: rightsLabel(preview.target.rights) });
  return t('The ACL of this folder was never read: the change cannot be compared.');
}

const names = (v: Record<string, unknown>) => {
  const list = Array.isArray(v.names) ? (v.names as unknown[]).map(String) : [];
  return list.join(', ') + (Number(v.count ?? list.length) > list.length ? ', …' : '');
};

export function riskSentence(risk: AclPreview['risks'][number]): string {
  const v = risk.values ?? {};
  switch (risk.code) {
    case 'SHARE_ROOT_WRITE': return t('Write at the root of the share {path}: the whole share becomes writable.', { path: String(v.path ?? '') });
    case 'ACL_NOT_READ': return t('The ACL was never read: read it from the Permissions tab of the folder before approving.');
    case 'ACL_READ_OLD': return t('The ACL was read {days} days ago: read it again from the Permissions tab before approving.', { days: v.days });
    case 'BROAD_ACCESS': return t('The folder is already open to the whole company: {names}.', { names: names(v) });
    case 'MANUAL_ENTRIES': return t('{count} entry(ies) set by hand outside BornToShare: {names}.', { count: v.count, names: names(v) });
    case 'DENY_ENTRIES': return t('{count} DENY entry(ies) may override this access: {names}.', { count: v.count, names: names(v) });
    case 'INHERITANCE_BROKEN': return t('This folder does not inherit from its parent: only its own entries apply.');
    default: return risk.code;
  }
}

export const RISK_CODES = ['SHARE_ROOT_WRITE', 'ACL_NOT_READ', 'ACL_READ_OLD', 'BROAD_ACCESS', 'MANUAL_ENTRIES', 'DENY_ENTRIES', 'INHERITANCE_BROKEN'];
