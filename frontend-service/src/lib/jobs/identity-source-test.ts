import { t } from '$lib/i18n';
import type { IdentitySourcePayload } from '$lib/api/identity-sources';
import { resolveCredentials } from '$lib/api/credentials';
import { notifyError, toUiAppError } from '$lib/errors';
import { toast } from '$lib/stores/toast';
import { buildIdentitySourceProbeRequest } from './probe-runner';
import { runProbeWithUi } from './probe-ui';

type FetchLike = typeof fetch;

export type IdentitySourceTestPayload = IdentitySourcePayload & {
  /** Plain bind password typed in the wizard, stored as a secret before probing */
  _secret?: string;
  bind_password?: string | null;
};

export type IdentitySourceTestResult = {
  ok: boolean;
  checks: Array<{ key: string; ok: boolean; message: string }>;
  status?: string | null;
  job_id?: string | number | null;
};

/**
 * Probe the LDAP connection described by `payload` (wizard or edit form).
 * A plain password is first stored in the secret broker, the probe only receives a secret_ref.
 */
export async function testIdentitySourceConnection(
  fetchFn: FetchLike,
  payload: IdentitySourceTestPayload
): Promise<IdentitySourceTestResult> {
  const protocol = (payload.protocol || 'ldaps').toLowerCase();
  const authMode = payload?.capabilities?.auth_mode === 'kerberos' ? 'kerberos' : 'ntlm';

  let secretRef: string | undefined = payload.bind_password_ref || undefined;
  const bindSecret = payload._secret ?? payload.bind_password;

  if (!secretRef && bindSecret) {
    try {
      const resolved = await resolveCredentials(fetchFn, {
        username: payload.bind_dn ?? null,
        password: bindSecret ?? null,
        secret_ref: payload.bind_password_ref ?? null
      }, { secretName: `identity-source/${protocol}/${payload.host || 'ad'}`, mode: 'create' });
      secretRef = resolved.secret_ref ?? undefined;
    } catch (e: unknown) {
      const appError = toUiAppError(e, t('Unable to store secret.'), 'auth', {
        action: 'identity_sources.resolve_bind_secret'
      });
      notifyError(appError);
      throw appError;
    }
  }

  if (!secretRef && payload.bind_dn) {
    toast.error(t('Password is required to test the connection (no secret_ref available).'));
    throw new Error('Missing secret_ref for bind_dn');
  }

  const request = buildIdentitySourceProbeRequest({
    protocol,
    host: payload.host,
    port: payload.port,
    baseDn: payload.base_dn,
    bindDn: payload.bind_dn,
    secretRef,
    authMode,
    uiOrigin: 'wizard'
  });

  const finalStatus = await runProbeWithUi({
    fetchFn,
    request,
    intervalMs: 1500,
    maxAttempts: 30
  });
  const ok = Boolean(finalStatus?.ok ?? finalStatus?.result?.success === true);
  return {
    ok,
    checks: [
      {
        key: 'probe',
        ok,
        message: finalStatus?.result?.message || finalStatus?.errorMessage || (ok ? t('Probe OK') : t('Probe failed'))
      }
    ],
    status: finalStatus?.status,
    job_id: finalStatus?.jobId
  };
}
