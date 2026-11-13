/**
 * Copies a text. The Clipboard API exists only on HTTPS (or localhost): on an instance served over plain HTTP the
 * old way (a hidden text area and « copy ») takes over, so that « Copy » never silently does nothing.
 * Resolves true when the text was copied.
 */
export async function copyText(value: string): Promise<boolean> {
  if (!value) return false;
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* refused: try the old way */
  }
  if (typeof document === 'undefined') return false;
  const area = document.createElement('textarea');
  area.value = value;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.top = '-1000px';
  area.style.opacity = '0';
  const focused = document.activeElement as HTMLElement | null;
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  area.remove();
  focused?.focus?.();
  return ok;
}
