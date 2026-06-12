import { redirect, isRedirect } from '@sveltejs/kit';

export const actions = {
  default: async ({ fetch }) => {
    try {
      // Invalide la session côté auth-service via BFF direct
      await fetch('/api/auth/logout', {
        method: 'POST'
      });

      // Auth-service renvoie Set-Cookie (session expirée)
      throw redirect(303, '/login?toast=logged_out');
    } catch (err) {
      // Laisser passer les redirects SvelteKit
      if (isRedirect(err)) {
        throw err;
      }

      // Fallback sécurité : rediriger quand même
      throw redirect(303, '/login?toast=logged_out');
    }
  }
};
