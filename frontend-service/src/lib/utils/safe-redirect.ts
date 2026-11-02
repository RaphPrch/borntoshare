/** Only a path of this site: the sign-in page must not send anyone elsewhere (open redirect). */
export function safeInternalPath(value: string | null | undefined, fallback = '/dashboard'): string {
  const target = String(value ?? '').trim();
  if (!target.startsWith('/') || target.startsWith('//') || /[\\\u0000-\u001f]/.test(target)) return fallback;
  return target;
}
