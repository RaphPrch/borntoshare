/**
 * Shared host/IP validation utilities for BornToShare (frontend).
 * V1 goal: centralize hostname/IP parsing so Identity Sources and Storage Endpoints behave the same.
 */

export function isValidIPv4(input?: string | null): boolean {
  const s = (input ?? '').trim();
  if (!s) return false;
  const parts = s.split('.');
  if (parts.length !== 4) return false;
  for (const p of parts) {
    if (!/^[0-9]+$/.test(p)) return false;
    // avoid "01" ambiguity, but allow "0"
    if (p.length > 1 && p.startsWith('0')) return false;
    const n = Number(p);
    if (!Number.isInteger(n) || n < 0 || n > 255) return false;
  }
  return true;
}

/**
 * RFC-ish hostname validation (pragmatic). Accepts:
 * - labels a-zA-Z0-9, hyphen
 * - dot separated, 1..253 chars
 * - no leading/trailing hyphen per label
 */
export function isValidHostname(input?: string | null): boolean {
  const s = (input ?? '').trim();
  if (!s) return false;
  if (s.length > 253) return false;

  // allow single-label hostnames (intranet), but not purely numeric (reserved for IPv4-like)
  const labels = s.split('.');
  for (const label of labels) {
    if (!label) return false;
    if (label.length > 63) return false;
    if (!/^[A-Za-z0-9-]+$/.test(label)) return false;
    if (label.startsWith('-') || label.endsWith('-')) return false;
  }

  // if it's all digits and dots, it's not a hostname (likely malformed ipv4)
  if (/^[0-9.]+$/.test(s)) return false;

  return true;
}
