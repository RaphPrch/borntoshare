import { t } from '$lib/i18n';
import { intlLocale } from '$lib/i18n';
// Display formatting shared by every screen (dates, initials).

const DATE_OPTIONS: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric' };
const TIME_OPTIONS: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };

const toValidDate = (value: unknown): Date | null => {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** dd/mm/yyyy hh:mm (optionally :ss). Empty input -> `empty`; unparsable input is shown as-is. */
export function formatDateTime(
  value: unknown,
  { seconds = false, empty = '—' }: { seconds?: boolean; empty?: string } = {}
): string {
  const raw = String(value ?? '').trim();
  if (!raw) return empty;
  const date = toValidDate(raw);
  if (!date) return raw;
  return date.toLocaleString(intlLocale(), {
    ...DATE_OPTIONS,
    ...TIME_OPTIONS,
    ...(seconds ? { second: '2-digit' } : {})
  });
}

/** dd/mm/yyyy. Empty input -> `empty`; unparsable input is shown as-is. */
export function formatDate(value: unknown, { empty = '—' }: { empty?: string } = {}): string {
  const raw = String(value ?? '').trim();
  if (!raw) return empty;
  const date = toValidDate(raw);
  return date ? date.toLocaleDateString(intlLocale(), DATE_OPTIONS) : raw;
}

/** Two-letter initials: "Jane Doe" -> "JD", "john.doe" -> "JD", "System" -> "SY". */
export function initials(value?: string | null, fallback = '??'): string {
  const raw = String(value ?? '').trim();
  if (!raw) return fallback;
  const parts = raw.split(/[\s._-]+/).filter(Boolean);
  const first = (parts[0]?.[0] ?? '').toUpperCase();
  const second = (parts[1]?.[0] ?? parts[0]?.[1] ?? '').toUpperCase();
  return `${first}${second}`.trim() || fallback;
}

/** Compact relative time: "42s ago", "5m ago", "3h ago", "2d ago". */
export function timeAgo(iso?: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return t('{sec}s ago', { sec });
  const min = Math.floor(sec / 60);
  if (min < 60) return t('{min}m ago', { min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t('{hr}h ago', { hr });
  return t('{floor}d ago', { floor: Math.floor(hr / 24) });
}

/** Long technical values (DN, templates, paths): allow line breaks after , } \\ / only, never inside words. */
export function breakable(value: unknown): string {
  return String(value ?? '').replace(/([,}\\/])/g, '$1\u200b');
}
