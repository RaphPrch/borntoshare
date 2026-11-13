// svelte.config.js — SvelteKit 2 + Node Adapter

import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const config = {
  preprocess: vitePreprocess(),

  onwarn: (warning, handler) => {
    const ignoredCodes = new Set([
      'a11y_label_has_associated_control',
      'a11y_click_events_have_key_events',
      'a11y_consider_explicit_label',
      'a11y_role_supports_aria_props'
    ]);

    if (ignoredCodes.has(warning?.code)) return;
    handler(warning);
  },

  // Svelte 5 runes everywhere: a component written the former way (export let, $:, slots) no longer compiles.
  // (No third-party Svelte library in the app; one written the former way would need an exception here.)
  compilerOptions: { runes: true },

  kit: {
    // CSRF: SvelteKit only accepts form POSTs whose Origin matches the app origin,
    // which adapter-node takes from the ORIGIN env var (see podman-compose.yml).
    adapter: adapter(),
    // Content-Security-Policy: scripts of the app only (SvelteKit adds a nonce to the ones it inlines), nothing
    // from elsewhere, and never shown in a frame. Styles allow inline: Svelte writes style="…" attributes.
    csp: {
      mode: 'auto',
      directives: {
        'default-src': ['self'],
        'script-src': ['self'],
        'style-src': ['self', 'unsafe-inline'],
        'img-src': ['self', 'data:', 'blob:'],
        'font-src': ['self', 'data:'],
        'connect-src': ['self'],
        'object-src': ['none'],
        'base-uri': ['self'],
        'form-action': ['self'],
        'frame-ancestors': ['none']
      }
    }
  }
};

export default config;
