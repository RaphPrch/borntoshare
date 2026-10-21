import type { Me } from './lib/types/me';
import type { Locale } from './lib/i18n';

declare global {
  namespace App {
    interface Locals {
      me: Me | null;
      locale: Locale;
    }
  }
}

export {};

