import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { toAppError } from '$lib/core/errors';
import { logAppError } from '$lib/core/logging';

export const POST: RequestHandler = async ({ fetch }) => {
  let res: Response;

  try {
    // Passe par hooks.server.ts → auth-service
    res = await fetch('/api/auth/logout', {
      method: 'POST'
    });
  } catch (err) {
    const appError = toAppError(err, { source: 'ssr' });
    logAppError(appError, {
      action: 'auth.logout.upstream_unreachable',
      route: '/logout'
    });
    return json(
      { message: 'Authentication service unreachable' },
      { status: 503 }
    );
  }

  if (!res.ok) {
    return json(
      { message: 'Logout failed' },
      { status: res.status }
    );
  }

  // Auth-service renvoie Set-Cookie (session expirée)
  return json({ ok: true });
};
