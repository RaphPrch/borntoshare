import type { Me } from './lib/types/me';

declare global {
  namespace App {
    interface Locals {
      me: Me | null;
    }
  }
}

export {};

