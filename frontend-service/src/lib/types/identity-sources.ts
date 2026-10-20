/** Identity source as returned by GET /identity-sources (plus internal metadata). */
export type IdentitySourceRow = {
  id: number;
  type?: string;
  name?: string;
  display_name?: string;
  protocol?: 'ldap' | 'ldaps' | string;
  host?: string;
  port?: number;
  base_dn?: string;
  bind_dn?: string;
  bind_password_ref?: string;
  issuer_url?: string;
  client_id?: string;
  status?: string;
  is_active?: boolean;
  used?: boolean;
  last_probe_at?: string | null;
  probed_at?: string | null;
  last_probe_message?: string | null;
  last_snapshot_at?: string | null;
  snapshot_at?: string | null;
  last_sync_at?: string | null;
  last_snapshot_status?: string | null;
  last_snapshot_version?: number | null;
  last_snapshot_objects_count?: number | null;
  last_snapshot_users_count?: number | null;
  last_snapshot_groups_count?: number | null;
  last_snapshot_memberships_count?: number | null;
  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    auth_mode?: 'ntlm' | 'kerberos' | string;
    snapshot_enabled?: boolean;
  };
  updated_at?: string | null;
};
