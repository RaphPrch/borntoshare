import type { FetchLike } from '$lib/api/client';
import { apiPost } from '$lib/api/client';
import type { CredentialsInput, CredentialsMode, ResolvedCredentials } from './credentials-types';

export type ResolveCredentialsOptions = {
  /**
   * Human-readable backend secret name. The frontend sends it to auth-service,
   * which stores the value and returns a secret_ref.
   * Example: "identity-source/ldaps/ad01" or "storage-endpoint/smb/nas01".
   */
  secretName: string;

  /**
   * create: if password provided, always store and return secret_ref
   * edit: if password provided, store; otherwise keep existing secret_ref
   */
  mode?: CredentialsMode;
};

type StoreCredentialSecretResponse = {
  bind_password_ref?: string | null;
};

function unwrapSecretRefResponse(payload: unknown): StoreCredentialSecretResponse {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {};
  }
  const record = payload as Record<string, unknown>;
  const data = record.data && typeof record.data === 'object' && !Array.isArray(record.data)
    ? record.data as Record<string, unknown>
    : record;
  return {
    bind_password_ref: typeof data.bind_password_ref === 'string' ? data.bind_password_ref : null
  };
}

function resolveCredentialSecretPath(secretName: string): string {
  if (secretName.startsWith('storage-endpoint/')) {
    return '/storage-endpoints/secret-ref';
  }
  return '/identity-sources/secret-ref';
}

/**
 * Resolve credentials in a secure way:
 * - Never returns plaintext password
 * - If password is provided, asks auth-service to store it and returns secret_ref
 * - If password is not provided, keeps the existing secret_ref (if any)
 */
export async function resolveCredentials(
  fetchFn: FetchLike,
  input: CredentialsInput,
  options: ResolveCredentialsOptions
): Promise<ResolvedCredentials> {
  const mode: CredentialsMode = options.mode ?? 'create';
  const username = (input.username ?? '').trim() || null;
  const password = (input.password ?? '').trim() || null;
  const secretRef = (input.secret_ref ?? '').trim() || null;

  // No username => consider credentials absent.
  if (!username) return { username: null, secret_ref: null };

  // If user provided a new password, store it and return secret_ref.
  if (password) {
    const stored = unwrapSecretRefResponse(await apiPost<unknown>(fetchFn, resolveCredentialSecretPath(options.secretName), {
      type: 'ad',
      name: options.secretName,
      protocol: options.secretName.split('/')[1] || undefined,
      host: options.secretName.split('/')[2] || undefined,
      bind_dn: username,
      bind_password: password,
      bind_password_ref: secretRef
    }));
    return { username, secret_ref: stored?.bind_password_ref ?? null };
  }

  // Edit mode: keep existing secret_ref.
  if (mode === 'edit') {
    return { username, secret_ref: secretRef };
  }

  // Create mode: allow secret_ref if user selected an existing secret.
  return { username, secret_ref: secretRef };
}
