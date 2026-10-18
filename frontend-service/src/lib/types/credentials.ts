export type CredentialsMode = 'create' | 'edit';

/**
 * Generic username/password-or-secret_ref input.
 * - password is UI-only
 * - secret_ref is persisted and resolved by backend services
 */
export type CredentialsInput = {
  username?: string | null;
  password?: string | null;
  secret_ref?: string | null;
};

export type ResolvedCredentials = {
  username?: string | null;
  secret_ref?: string | null;
};
