import { fail, redirect, isRedirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
/* -----------------------------------------
 * LOAD
 * --------------------------------------- */
export const load: PageServerLoad = async ({ fetch, locals, url }) => {
  // 🔐 ALREADY AUTHENTICATED → REDIRECT
  if (locals.me?.id) {
    throw redirect(302, '/dashboard');
  }

  // SSO buttons (Keycloak providers enabled in Advanced Settings › Infrastructure)
  const sso = await fetch('/api/auth/sso/providers', { headers: { accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  const ssoProviders = Array.isArray(sso?.providers)
    ? sso.providers.map((p: { id: number; label: string }) => ({ id: Number(p.id), label: String(p.label) }))
    : [];
  const common = { ssoProviders, ssoError: url.searchParams.get('sso_error'), redirectTo: url.searchParams.get('redirect') };

  try {
    const res = await fetch('/api/auth/providers', {
      headers: { accept: 'application/json' },
      credentials: 'include'
    });

    const data = await res.json().catch(() => ({}));

    return {
      ...common,
      providers: {
        default: data?.default ?? 'local',
        enabled: Array.isArray(data?.enabled) ? data.enabled : [],
        available: Array.isArray(data?.available) ? data.available : []
      }
    };
  } catch (err) {
    // Safe fallback (offline / degraded mode)
    return {
      ...common,
      providers: {
        default: 'local',
        enabled: ['local'],
        available: ['local']
      }
    };
  }
};

/* -----------------------------------------
 * ACTION
 * --------------------------------------- */
export const actions: Actions = {
  default: async ({ request, url, fetch }) => {
    const form = await request.formData();
    const username = form.get('username')?.toString().trim();
    const password = form.get('password')?.toString();
    const provider =
      form.get('provider')?.toString().trim() || undefined;

    if (!username || !password) {
      return fail(400, {
        error: 'Missing credentials.',
        toast: {
          type: 'error',
          message: 'Missing credentials.',
          duration: 3500
        }
      });
    }

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          accept: 'application/json'
        },
        credentials: 'include', // 🔥 REQUIRED FOR COOKIE SESSION
        body: JSON.stringify({
          username,
          password,
          ...(provider ? { provider } : {})
        })
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        const payloadMessage =
          (typeof payload?.error?.message === 'string' && payload.error.message.trim()) ||
          (typeof payload?.detail?.message === 'string' && payload.detail.message.trim()) ||
          (typeof payload?.detail === 'string' && payload.detail.trim()) ||
          (typeof payload?.error === 'string' && payload.error.trim()) ||
          null;
        let msg = 'Login failed.';

        if (res.status === 401) {
          msg = 'Invalid username or password.';
        } else if (res.status === 403 && payloadMessage) {
          msg = payloadMessage;
        } else if (res.status === 429) {
          msg = 'Too many failed sign-in attempts. Try again later.';
        } else if (res.status >= 500) {
          msg = 'Authentication service unavailable.';
        } else if (payloadMessage) {
          msg = payloadMessage;
        }

        return fail(res.status, {
          error: msg,
          toast: {
            type: 'error',
            message: msg,
            duration: 4000
          }
        });
      }

      const target =
        url.searchParams.get('redirect') || '/dashboard';

      // 🔐 Auth is successful — let hooks + layout handle protection
      throw redirect(303, target);
    } catch (err: unknown) {
      if (isRedirect(err)) throw err;

      return fail(503, {
        error: 'Authentication service unavailable.',
        toast: {
          type: 'error',
          message: 'Authentication service unavailable.',
          duration: 4500
        }
      });
    }
  }
};
