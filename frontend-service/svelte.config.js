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
      'a11y_role_supports_aria_props',
      'export_let_unused',
      'css_unused_selector'
    ]);

    if (ignoredCodes.has(warning?.code)) return;
    handler(warning);
  },

  kit: {
    // CSRF: SvelteKit only accepts form POSTs whose Origin matches the app origin,
    // which adapter-node takes from the ORIGIN env var (see podman-compose.yml).
    adapter: adapter()
  }
};

export default config;
