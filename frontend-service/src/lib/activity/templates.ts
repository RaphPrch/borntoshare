export type ActivityTemplate = {
  titleKey: string;
  descriptionKey: string;
  badge?: 'info' | 'admin' | 'critical';
  scope?: 'business' | 'security';
  icon?: string; // bootstrap icon name
};

export const activityTemplates: Record<string, ActivityTemplate> = {
  // Zones
  'zone.created': { titleKey: 'activity.zone.created.title', descriptionKey: 'activity.zone.created.description', badge: 'info', icon: 'plus-circle' },
  'zone.updated': { titleKey: 'activity.zone.updated.title', descriptionKey: 'activity.zone.updated.description', badge: 'info', icon: 'pencil-square' },
  'zone.deleted': { titleKey: 'activity.zone.deleted.title', descriptionKey: 'activity.zone.deleted.description', badge: 'critical', scope: 'security', icon: 'trash3' },
  'zone.policy_saved': { titleKey: 'activity.zone.policy_saved.title', descriptionKey: 'activity.zone.policy_saved.description', badge: 'admin', scope: 'security', icon: 'shield-check' },
  'zone.provisioning_settings_saved': { titleKey: 'activity.zone.provisioning_settings_saved.title', descriptionKey: 'activity.zone.provisioning_settings_saved.description', badge: 'admin', scope: 'security', icon: 'shield-check' },
  'zone.profile_attached': { titleKey: 'activity.zone.profile_attached.title', descriptionKey: 'activity.zone.profile_attached.description', badge: 'admin', icon: 'link-45deg' },
  'zone.profile_detached': { titleKey: 'activity.zone.profile_detached.title', descriptionKey: 'activity.zone.profile_detached.description', badge: 'admin', icon: 'unlink' },
  'zone.probe_rerun': { titleKey: 'activity.zone.probe_rerun.title', descriptionKey: 'activity.zone.probe_rerun.description', badge: 'info', icon: 'arrow-repeat' },

  // Endpoints
  'storage_endpoint.created': { titleKey: 'activity.storage_endpoint.created.title', descriptionKey: 'activity.storage_endpoint.created.description', badge: 'admin', icon: 'hdd-network' },
  'storage_endpoint.updated': { titleKey: 'activity.storage_endpoint.updated.title', descriptionKey: 'activity.storage_endpoint.updated.description', badge: 'admin', icon: 'hdd-network' },
  'storage_endpoint.deleted': { titleKey: 'activity.storage_endpoint.deleted.title', descriptionKey: 'activity.storage_endpoint.deleted.description', badge: 'critical', scope: 'security', icon: 'trash3' },

  // Tags
  'tag.created': { titleKey: 'activity.tag.created.title', descriptionKey: 'activity.tag.created.description', badge: 'admin', icon: 'tag' },
  'tag.updated': { titleKey: 'activity.tag.updated.title', descriptionKey: 'activity.tag.updated.description', badge: 'admin', icon: 'tag' },
  'tag.deleted': { titleKey: 'activity.tag.deleted.title', descriptionKey: 'activity.tag.deleted.description', badge: 'critical', scope: 'security', icon: 'tag' },
  'tag.attached': { titleKey: 'activity.tag.attached.title', descriptionKey: 'activity.tag.attached.description', badge: 'info', icon: 'tag' },
  'tag.detached': { titleKey: 'activity.tag.detached.title', descriptionKey: 'activity.tag.detached.description', badge: 'info', icon: 'tag' },

  // Storage roots
  'storage_root.created': { titleKey: 'activity.storage_root.created.title', descriptionKey: 'activity.storage_root.created.description', badge: 'admin', icon: 'folder-plus' },
  'storage_root.updated': { titleKey: 'activity.storage_root.updated.title', descriptionKey: 'activity.storage_root.updated.description', badge: 'admin', icon: 'folder' },
  'storage_root.deleted': { titleKey: 'activity.storage_root.deleted.title', descriptionKey: 'activity.storage_root.deleted.description', badge: 'admin', icon: 'folder-x' },
  'storage_root.owners.replaced': { titleKey: 'activity.storage_root.owners.replaced.title', descriptionKey: 'activity.storage_root.owners.replaced.description', badge: 'admin', icon: 'people' },
  'storage_root.role.assigned': { titleKey: 'activity.storage_root.role.assigned.title', descriptionKey: 'activity.storage_root.role.assigned.description', badge: 'admin', icon: 'person-check' },
  'storage_root.role.removed': { titleKey: 'activity.storage_root.role.removed.title', descriptionKey: 'activity.storage_root.role.removed.description', badge: 'admin', icon: 'person-dash' },
  'storage_root.probe_rerun': { titleKey: 'activity.storage_root.probe_rerun.title', descriptionKey: 'activity.storage_root.probe_rerun.description', badge: 'info', icon: 'arrow-repeat' },

  // Access profiles
  'access_profile.created': { titleKey: 'activity.access_profile.created.title', descriptionKey: 'activity.access_profile.created.description', badge: 'admin', icon: 'badge-ad' },
  'access_profile.updated': { titleKey: 'activity.access_profile.updated.title', descriptionKey: 'activity.access_profile.updated.description', badge: 'admin', icon: 'badge-ad' },
  'access_profile.deleted': { titleKey: 'activity.access_profile.deleted.title', descriptionKey: 'activity.access_profile.deleted.description', badge: 'admin', icon: 'badge-ad' },
  'access_profile.subject.added': { titleKey: 'activity.access_profile.subject.added.title', descriptionKey: 'activity.access_profile.subject.added.description', badge: 'admin', icon: 'person-plus' },
  'access_profile.subject.removed': { titleKey: 'activity.access_profile.subject.removed.title', descriptionKey: 'activity.access_profile.subject.removed.description', badge: 'admin', icon: 'person-dash' },

  // Requests
  'access_request.created': { titleKey: 'activity.access_request.created.title', descriptionKey: 'activity.access_request.created.description', badge: 'info', icon: 'inbox' },
  'access_request.approved': { titleKey: 'activity.access_request.approved.title', descriptionKey: 'activity.access_request.approved.description', badge: 'admin', icon: 'check2-circle' },
  'access_request.rejected': { titleKey: 'activity.access_request.rejected.title', descriptionKey: 'activity.access_request.rejected.description', badge: 'admin', icon: 'x-circle' },
  'access_request.executed': { titleKey: 'activity.access_request.executed.title', descriptionKey: 'activity.access_request.executed.description', badge: 'info', icon: 'check2-circle' },
  'access_request.failed': { titleKey: 'activity.access_request.failed.title', descriptionKey: 'activity.access_request.failed.description', badge: 'critical', scope: 'security', icon: 'exclamation-triangle' },

  // Identity sources / RBAC
  'identity_source.created': { titleKey: 'activity.identity_source.created.title', descriptionKey: 'activity.identity_source.created.description', badge: 'admin', scope: 'security', icon: 'person-badge' },
  'identity_source.updated': { titleKey: 'activity.identity_source.updated.title', descriptionKey: 'activity.identity_source.updated.description', badge: 'admin', scope: 'security', icon: 'person-badge' },
  'identity_source.deleted': { titleKey: 'activity.identity_source.deleted.title', descriptionKey: 'activity.identity_source.deleted.description', badge: 'critical', scope: 'security', icon: 'person-x' },
  'identity_source.sync_started': { titleKey: 'activity.identity_source.sync_started.title', descriptionKey: 'activity.identity_source.sync_started.description', badge: 'info', icon: 'arrow-repeat' },
  'identity_source.sync_failed': { titleKey: 'activity.identity_source.sync_failed.title', descriptionKey: 'activity.identity_source.sync_failed.description', badge: 'critical', scope: 'security', icon: 'exclamation-triangle' },

  'role.assigned': { titleKey: 'activity.role.assigned.title', descriptionKey: 'activity.role.assigned.description', badge: 'critical', scope: 'security', icon: 'key' },
  'role.revoked': { titleKey: 'activity.role.revoked.title', descriptionKey: 'activity.role.revoked.description', badge: 'admin', scope: 'security', icon: 'key' },

  // Provisioning (governance / audit)
  'ad_group_ensure_queued': { titleKey: 'activity.ad_group_ensure_queued.title', descriptionKey: 'activity.ad_group_ensure_queued.description', badge: 'info', icon: 'clock-history' },
  'access_profile_created': { titleKey: 'activity.access_profile_created.title', descriptionKey: 'activity.access_profile_created.description', badge: 'admin', icon: 'badge-ad' },
  'access_profile_deleted': { titleKey: 'activity.access_profile_deleted.title', descriptionKey: 'activity.access_profile_deleted.description', badge: 'critical', scope: 'security', icon: 'badge-ad' },
  'access_profile_provisioning_started': { titleKey: 'activity.access_profile_provisioning_started.title', descriptionKey: 'activity.access_profile_provisioning_started.description', badge: 'info', icon: 'play-circle' },
  'access_profile_provisioning_succeeded': { titleKey: 'activity.access_profile_provisioning_succeeded.title', descriptionKey: 'activity.access_profile_provisioning_succeeded.description', badge: 'info', icon: 'check2-circle' },
  'access_profile_provisioning_failed': { titleKey: 'activity.access_profile_provisioning_failed.title', descriptionKey: 'activity.access_profile_provisioning_failed.description', badge: 'critical', scope: 'security', icon: 'exclamation-triangle' },
  'access_profile_provisioning_retry': { titleKey: 'activity.access_profile_provisioning_retry.title', descriptionKey: 'activity.access_profile_provisioning_retry.description', badge: 'admin', icon: 'arrow-repeat' },
  'access_profile_provisioning_reconcile': { titleKey: 'activity.access_profile_provisioning_reconcile.title', descriptionKey: 'activity.access_profile_provisioning_reconcile.description', badge: 'admin', icon: 'diagram-3' },
  'profile_created': { titleKey: 'activity.profile_created.title', descriptionKey: 'activity.profile_created.description', badge: 'admin', icon: 'badge-ad' },
  'profile_provisioning_success': { titleKey: 'activity.profile_provisioning_success.title', descriptionKey: 'activity.profile_provisioning_success.description', badge: 'info', icon: 'check2-circle' },
  'profile_provisioning_failed': { titleKey: 'activity.profile_provisioning_failed.title', descriptionKey: 'activity.profile_provisioning_failed.description', badge: 'critical', scope: 'security', icon: 'exclamation-triangle' },
  'ensure_ad_group': { titleKey: 'activity.ensure_ad_group.title', descriptionKey: 'activity.ensure_ad_group.description', badge: 'admin', icon: 'people' },
  'ensure_ad_group_member': { titleKey: 'activity.ensure_ad_group_member.title', descriptionKey: 'activity.ensure_ad_group_member.description', badge: 'admin', icon: 'person-plus' },
  'remove_ad_group_member': { titleKey: 'activity.remove_ad_group_member.title', descriptionKey: 'activity.remove_ad_group_member.description', badge: 'admin', icon: 'person-dash' },
  'acl_apply_via_group': { titleKey: 'activity.acl_apply_via_group.title', descriptionKey: 'activity.acl_apply_via_group.description', badge: 'admin', icon: 'shield-check' },
  'provisioning_job_cancelled': { titleKey: 'activity.provisioning_job_cancelled.title', descriptionKey: 'activity.provisioning_job_cancelled.description', badge: 'critical', scope: 'security', icon: 'x-octagon' },
  'provisioning_job_watchdog_republish': { titleKey: 'activity.provisioning_job_watchdog_republish.title', descriptionKey: 'activity.provisioning_job_watchdog_republish.description', badge: 'info', icon: 'arrow-repeat' },
  'collect_directory_snapshot': { titleKey: 'activity.collect_directory_snapshot.title', descriptionKey: 'activity.collect_directory_snapshot.description', badge: 'info', icon: 'camera' },
  'discover_group_users_recursive': { titleKey: 'activity.discover_group_users_recursive.title', descriptionKey: 'activity.discover_group_users_recursive.description', badge: 'info', icon: 'diagram-3' },
  'search_ldap_principals': { titleKey: 'activity.search_ldap_principals.title', descriptionKey: 'activity.search_ldap_principals.description', badge: 'info', icon: 'search' },
  'search_ldaps_principals': { titleKey: 'activity.search_ldaps_principals.title', descriptionKey: 'activity.search_ldaps_principals.description', badge: 'info', icon: 'search' },
  'test_ldap': { titleKey: 'activity.test_ldap.title', descriptionKey: 'activity.test_ldap.description', badge: 'info', icon: 'activity' },
  'test_ldaps': { titleKey: 'activity.test_ldaps.title', descriptionKey: 'activity.test_ldaps.description', badge: 'info', icon: 'activity' },
  'test_kerberos': { titleKey: 'activity.test_kerberos.title', descriptionKey: 'activity.test_kerberos.description', badge: 'info', icon: 'activity' },
  'test_smb_ntlm': { titleKey: 'activity.test_smb_ntlm.title', descriptionKey: 'activity.test_smb_ntlm.description', badge: 'info', icon: 'activity' },
  'secret_resolve': { titleKey: 'activity.secret_resolve.title', descriptionKey: 'activity.secret_resolve.description', badge: 'admin', scope: 'security', icon: 'key' },
  'identity_source_create_snapshot_trigger': { titleKey: 'activity.identity_source_create_snapshot_trigger.title', descriptionKey: 'activity.identity_source_create_snapshot_trigger.description', badge: 'info', icon: 'camera' },
  'governance_get': { titleKey: 'activity.governance_get.title', descriptionKey: 'activity.governance_get.description', badge: 'info', icon: 'cloud-download' },
  'governance_post': { titleKey: 'activity.governance_post.title', descriptionKey: 'activity.governance_post.description', badge: 'info', icon: 'cloud-upload' },
  'activity_create': { titleKey: 'activity.activity_create.title', descriptionKey: 'activity.activity_create.description', badge: 'info', icon: 'journal-plus' },
  'activity_write': { titleKey: 'activity.activity_write.title', descriptionKey: 'activity.activity_write.description', badge: 'info', icon: 'journal-check' },
  'activity_list_latest': { titleKey: 'activity.activity_list_latest.title', descriptionKey: 'activity.activity_list_latest.description', badge: 'info', icon: 'clock-history' },
  'activity_list_by_target': { titleKey: 'activity.activity_list_by_target.title', descriptionKey: 'activity.activity_list_by_target.description', badge: 'info', icon: 'filter' },
  'activity_list_by_actor': { titleKey: 'activity.activity_list_by_actor.title', descriptionKey: 'activity.activity_list_by_actor.description', badge: 'info', icon: 'person-lines-fill' },
  'validate_internal_headers': { titleKey: 'activity.validate_internal_headers.title', descriptionKey: 'activity.validate_internal_headers.description', badge: 'critical', scope: 'security', icon: 'shield-lock' },
  'validate_service_token': { titleKey: 'activity.validate_service_token.title', descriptionKey: 'activity.validate_service_token.description', badge: 'critical', scope: 'security', icon: 'shield-lock' },
  'validation_error': { titleKey: 'activity.validation_error.title', descriptionKey: 'activity.validation_error.description', badge: 'critical', scope: 'security', icon: 'exclamation-octagon' },
  'http_exception': { titleKey: 'activity.http_exception.title', descriptionKey: 'activity.http_exception.description', badge: 'critical', scope: 'security', icon: 'exclamation-triangle' },
  'unhandled_exception': { titleKey: 'activity.unhandled_exception.title', descriptionKey: 'activity.unhandled_exception.description', badge: 'critical', scope: 'security', icon: 'bug' },
  'member_added': { titleKey: 'activity.member_added.title', descriptionKey: 'activity.member_added.description', badge: 'admin', icon: 'person-plus' },
  'member_removed': { titleKey: 'activity.member_removed.title', descriptionKey: 'activity.member_removed.description', badge: 'admin', icon: 'person-dash' },
  'access_policy_updated': { titleKey: 'activity.access_policy_updated.title', descriptionKey: 'activity.access_policy_updated.description', badge: 'admin', scope: 'security', icon: 'shield-check' },

  // Security / config
  'security.policy_changed': { titleKey: 'activity.security.policy_changed.title', descriptionKey: 'activity.security.policy_changed.description', badge: 'critical', scope: 'security', icon: 'shield-exclamation' },
  'security.config_updated': { titleKey: 'activity.security.config_updated.title', descriptionKey: 'activity.security.config_updated.description', badge: 'high', scope: 'security', icon: 'shield-check' } as any
};
