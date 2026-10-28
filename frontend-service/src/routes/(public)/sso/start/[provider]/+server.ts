import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

/** Login page button: asks auth-service for the Keycloak URL, then sends the browser there. */
export const GET: RequestHandler = async ({ params, url, fetch }) => {
  const providerId = Number(params.provider);
  if (!Number.isInteger(providerId) || providerId <= 0) throw redirect(303, '/login');

  const res = await fetch('/api/auth/sso/start', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({
      provider_id: providerId,
      redirect_uri: `${url.origin}/sso/callback`,
      return_to: url.searchParams.get('redirect') || '/dashboard'
    })
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.authorization_url) {
    const message = data?.error?.message ?? 'The sign-in with your organization is unavailable.';
    throw redirect(303, `/login?sso_error=${encodeURIComponent(message)}`);
  }
  throw redirect(303, data.authorization_url);
};
