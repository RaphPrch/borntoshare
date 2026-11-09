import { t } from '$lib/i18n';

/**
 * How to resolve each kind of governance alert: why it is raised, the steps, where to act.
 * The checks of BornToShare close an alert by themselves once the cause is gone; marking it resolved
 * by hand only hides it until the next check finds the cause again.
 */
export type AlertGuide = { cause: string; steps: string[]; action?: { label: string; tab?: string } };

const GUIDES: Record<string, () => AlertGuide> = {
  sensitivity_remediation: () => ({
    cause: t('An administrator asked the guardians to remove the files holding passwords found in this folder, before a due date.'),
    steps: [
      t('Open the folder: the Sensitivity card lists the files concerned.'),
      t('Move the accesses into a password vault, then delete the files (or mark a real false positive).'),
      t('The next scan closes the correction by itself; at the due date the folder is scanned again automatically.')
    ],
    action: { label: t('Open the folder') }
  }),
  acl_principal_not_governed: () => ({
    cause: t('A user or a group holds a right written straight in the NTFS ACL of the folder, outside the groups that BornToShare governs.'),
    steps: [
      t('Open the Permissions tab of the folder and find the entry marked « not governed ».'),
      t('If the access is legitimate, ask for it through a request so that it goes through the governed group.'),
      t('Then remove the direct entry from the ACL (Permissions › Repair, or on the server).'),
      t('Run « Reread the ACL »: the alert closes by itself when the entry is gone.')
    ],
    action: { label: t('Open the permissions'), tab: 'permissions' }
  }),
  acl_inherited_not_governed: () => ({
    cause: t('A right inherited from a parent folder reaches this folder without going through a governed group.'),
    steps: [
      t('Find the parent folder that carries the right (Permissions tab, « inherited from » column).'),
      t('Remove the entry on the parent, or break the inheritance on this folder if it must be governed alone.'),
      t('Reread the ACL to check.')
    ],
    action: { label: t('Open the permissions'), tab: 'permissions' }
  }),
  acl_profile_missing: () => ({
    cause: t('A governed group (read or modify) is missing from the ACL of the folder: its members do not get the access they were granted.'),
    steps: [
      t('Open the Permissions tab and use « Repair »: BornToShare writes the missing entries.'),
      t('If the repair fails, check that the worker account is allowed to change the ACL on the server.'),
      t('Reread the ACL.')
    ],
    action: { label: t('Open the permissions'), tab: 'permissions' }
  }),
  acl_propagation_failed: () => ({
    cause: t('Writing the rights on the folder failed (access refused, path not found or server unreachable).'),
    steps: [
      t('Read the error in the Activity tab of the folder.'),
      t('Check that the server answers and that the worker account still has the right to change permissions.'),
      t('Run the repair again from the Permissions tab.')
    ],
    action: { label: t('Open the activity'), tab: 'activity' }
  }),
  ad_group_read_failed: () => ({
    cause: t('The worker could not read a governed group in Active Directory (group deleted, renamed or account without read right).'),
    steps: [
      t('Check in Active Directory that the group still exists under the expected OU.'),
      t('Check the account of the directory (Directories › Test the connection).'),
      t('Reread the folder: the alert closes once the group is read.')
    ]
  }),
  ad_member_missing: () => ({
    cause: t('A person was granted access but is not a member of the AD group: the access was not written, or was removed by hand in AD.'),
    steps: [
      t('Open the request of the person (Requests) and replay its execution.'),
      t('If someone removed the member in AD on purpose, revoke the access in BornToShare instead.')
    ]
  }),
  ad_member_not_granted: () => ({
    cause: t('Someone is a member of the AD group without any access granted in BornToShare (added straight in AD).'),
    steps: [
      t('If the access is legitimate, have it requested and approved so that it is traced.'),
      t('Otherwise remove the member from the group in AD.')
    ]
  }),
  endpoint_unreachable: () => ({
    cause: t('The worker cannot reach the file server: network, DNS, SMB port 445 closed, or the account refused.'),
    steps: [
      t('Check that the server is up and answers on port 445 from the worker.'),
      t('If its address changed, update it on the server page (Servers › Edit).'),
      t('Test the connection: the alerts of its folders close at the next check.')
    ],
    action: { label: t('Open the server') }
  }),
  root_probe_failed: () => ({
    cause: t('The last test of the folder failed: share missing, path renamed or access refused.'),
    steps: [
      t('Read the message of the test on the folder.'),
      t('If the folder was moved or renamed, update its path; if it was deleted, remove it from BornToShare.'),
      t('Run « Test » again.')
    ]
  }),
  root_probe_unknown: () => ({
    cause: t('The folder has never been tested: its state is not known.'),
    steps: [t('Run « Test » on the folder, or a check of every folder from the server page.')]
  }),
  missing_guardian: () => ({
    cause: t('The folder has no guardian (or not enough): only the administrators can validate its requests.'),
    steps: [
      t('Open the folder and add at least one guardian (Governance › Guardians).'),
      t('To do it for many folders: select them in the list, then « Guardians ».')
    ],
    action: { label: t('Open the folder') }
  }),
  pending_access_validation: () => ({
    cause: t('A request has been waiting for validation for too long.'),
    steps: [
      t('Open Requests and approve or refuse it.'),
      t('If the guardian is absent, add another guardian to the folder.')
    ]
  })
};

export const alertGuide = (alertType: string | null | undefined): AlertGuide => {
  const key = String(alertType ?? '').split(':')[0].trim().toLowerCase();
  if (key === 'policy')
    return {
      cause: t('The folder matches a smart policy: its condition is shown under the title.'),
      steps: [
        t('Open the folder and correct what the condition points at (sensitive files, missing guardian, size…).'),
        t('At its next run, the policy closes the alert by itself once the folder no longer matches.'),
        t('If the policy is wrong, change its condition on the Policies page.')
      ],
      action: { label: t('Open the folder') }
    };
  const found = GUIDES[key] ?? (key.startsWith('ad_group') ? GUIDES.ad_group_read_failed : null);
  return found
    ? found()
    : {
        cause: t('BornToShare detected this problem during a check.'),
        steps: [t('Open the item concerned and correct the cause described in the message.'), t('Run its check again.')]
      };
};
