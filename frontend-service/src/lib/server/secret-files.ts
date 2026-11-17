import { readFileSync } from 'node:fs';

declare const process: {
  env: Record<string, string | undefined>;
};

const cache = new Map<string, string>();

/**
 * A secret of the server: NAME_FILE (a podman secret mounted in /run/secrets, or /etc/borntoshare/secrets without
 * container) read once, else NAME from the environment (development). As the Python services do (secret_files.py):
 * the value never sits in the environment of the container, where `podman inspect` would show it.
 */
export function serverSecret(name: string): string {
  const cached = cache.get(name);
  if (cached !== undefined) return cached;
  const path = (process.env[`${name}_FILE`] ?? '').trim();
  let value = (process.env[name] ?? '').trim();
  if (!value && path) {
    value = readFileSync(path, 'utf8').trim();
  }
  if (value) cache.set(name, value);
  return value;
}

/** Tests only: forget what was read. */
export function forgetServerSecrets(): void {
  cache.clear();
}
