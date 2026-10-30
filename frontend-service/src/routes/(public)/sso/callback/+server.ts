import type { RequestHandler } from './$types';

function toLogin(message: string): Response {
  return new Response(null, { status: 303, headers: { location: `/login?sso_error=${encodeURIComponent(message)}` } });
}

/** Return from Keycloak: auth-service checks the code and opens the session; its cookies go to the browser. */
export const GET: RequestHandler = async ({ url, fetch }) => {
  const error = url.searchParams.get('error');
  if (error) {
    return toLogin(error === 'access_denied' ? 'The sign-in was cancelled.' : 'The identity provider refused the sign-in.');
  }
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  if (!code || !state) return toLogin('Incomplete answer from the identity provider.');

  const res = await fetch('/api/auth/sso/callback', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({ code, state })
  });
  const data = await res.json().catch(() => null);
  // A malformed answer (422) has nothing useful to show: only a refusal explains itself
  if (!res.ok) return toLogin(res.status === 422 ? 'Sign-in failed.' : (data?.error?.message ?? 'Sign-in failed.'));

  const headers = new Headers({ location: String(data?.return_to || '/dashboard') });
  for (const cookie of res.headers.getSetCookie()) headers.append('set-cookie', cookie);
  return new Response(null, { status: 303, headers });
};
