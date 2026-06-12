
export type Role = 'admin' | 'user' | 'audit';
export type IdentitySource = 'ldap' | 'oidc' | 'local';

export type Identity = {
  id: string;
  display_name: string;
  source: IdentitySource;
  roles: Role[];
  is_active: boolean;
};
