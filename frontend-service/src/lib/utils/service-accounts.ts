import type { FetchLike } from '$lib/api/client';
import { resolveCredentials } from '$lib/api/credentials';
import type {
  ServiceAccountInput,
  ServiceAccountPublic,
  ServiceAccountPurpose
} from '$lib/api/identity-sources';

export const SERVICE_ACCOUNT_PURPOSES: ServiceAccountPurpose[] = ['snapshot', 'auth', 'provisioning'];

/** Form state of one dedicated account. The password lives only in the form, never in the payload. */
export type ServiceAccountDraft = {
  dedicated: boolean;
  bind_dn: string;
  password: string;
  /** A password is already stored for this account (edit mode) */
  has_password: boolean;
};

export type ServiceAccountDrafts = Record<ServiceAccountPurpose, ServiceAccountDraft>;

export function emptyServiceAccountDrafts(): ServiceAccountDrafts {
  return {
    snapshot: { dedicated: false, bind_dn: '', password: '', has_password: false },
    auth: { dedicated: false, bind_dn: '', password: '', has_password: false },
    provisioning: { dedicated: false, bind_dn: '', password: '', has_password: false }
  };
}

/** Accounts as listed (has_password) or as returned by the internal metadata (bind_password_ref). */
type StoredServiceAccount = Partial<ServiceAccountPublic> & { bind_password_ref?: string | null };

export function serviceAccountDraftsFrom(
  accounts: Partial<Record<ServiceAccountPurpose, StoredServiceAccount>> | null | undefined
): ServiceAccountDrafts {
  const drafts = emptyServiceAccountDrafts();
  for (const purpose of SERVICE_ACCOUNT_PURPOSES) {
    const account = accounts?.[purpose];
    if (account?.bind_dn) {
      drafts[purpose] = {
        dedicated: true,
        bind_dn: account.bind_dn,
        password: '',
        has_password: Boolean(account.has_password ?? account.bind_password_ref)
      };
    }
  }
  return drafts;
}

/** Purpose of the first incomplete dedicated account, or null when every account can be saved. */
export function serviceAccountDraftError(drafts: ServiceAccountDrafts): ServiceAccountPurpose | null {
  for (const purpose of SERVICE_ACCOUNT_PURPOSES) {
    const draft = drafts[purpose];
    if (!draft.dedicated) continue;
    if (!draft.bind_dn.trim() || (!draft.password.trim() && !draft.has_password)) return purpose;
  }
  return null;
}

/**
 * Store the new passwords in the secret broker and build `service_accounts` for the API.
 * An account switched off is sent as null (removed: back to the account of the source).
 * An account without a new password keeps its stored secret.
 */
export async function buildServiceAccountsPayload(
  fetchFn: FetchLike,
  drafts: ServiceAccountDrafts,
  secretNameBase: string
): Promise<Partial<Record<ServiceAccountPurpose, ServiceAccountInput>>> {
  const accounts: Partial<Record<ServiceAccountPurpose, ServiceAccountInput>> = {};
  for (const purpose of SERVICE_ACCOUNT_PURPOSES) {
    const draft = drafts[purpose];
    const bindDn = draft.bind_dn.trim();
    if (!draft.dedicated || !bindDn) {
      accounts[purpose] = null;
      continue;
    }
    if (!draft.password.trim()) {
      accounts[purpose] = { bind_dn: bindDn };
      continue;
    }
    const resolved = await resolveCredentials(
      fetchFn,
      { username: bindDn, password: draft.password, secret_ref: null },
      { secretName: `${secretNameBase}/${purpose}`, mode: 'create' }
    );
    accounts[purpose] = { bind_dn: bindDn, bind_password_ref: resolved.secret_ref ?? null };
  }
  return accounts;
}

type Capabilities = { auth?: boolean; snapshot_enabled?: boolean; provisioning?: boolean } | null | undefined;

export function capabilityEnabled(capabilities: Capabilities, purpose: ServiceAccountPurpose): boolean {
  if (purpose === 'snapshot') return capabilities?.snapshot_enabled === true;
  if (purpose === 'auth') return capabilities?.auth === true;
  return capabilities?.provisioning === true;
}

/** A disabled capability keeps no dedicated account. */
export function draftsForCapabilities(drafts: ServiceAccountDrafts, capabilities: Capabilities): ServiceAccountDrafts {
  const result = emptyServiceAccountDrafts();
  for (const purpose of SERVICE_ACCOUNT_PURPOSES) {
    if (capabilityEnabled(capabilities, purpose)) result[purpose] = drafts[purpose];
  }
  return result;
}

/** example.test from DC=example,DC=test (NetBIOS-less domain name used at sign-in). */
export function domainFromBaseDn(baseDn: string | null | undefined): string {
  return String(baseDn ?? '')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => /^dc=/i.test(part))
    .map((part) => part.slice(3).trim())
    .filter(Boolean)
    .join('.')
    .toLowerCase();
}
