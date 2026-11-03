import type { Me } from './lib/types/me';
import type { Locale } from './lib/i18n';

declare global {
  // Set at build time (vite.config.js)
  const __B2S_VERSION__: string;
  const __B2S_BUILT_AT__: string;

  namespace App {
    interface Locals {
      me: Me | null;
      locale: Locale;
    }
  }
}

export {};

