import { t } from '$lib/i18n';
import { toast } from '$lib/stores/toast';
import { copyText } from '$lib/utils/clipboard';

/**
 * Any element carrying `data-copy` copies that value (a UNC path, a reference) when clicked, with a short
 * confirmation. One listener for the whole app (layout); a click inside a link or button keeps its own action.
 */
export function installCopyOnClick(): () => void {
  if (typeof document === 'undefined') return () => {};
  const onClick = (event: MouseEvent) => {
    const target = event.target as HTMLElement | null;
    const el = target?.closest<HTMLElement>('[data-copy]');
    if (!el || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    // Selecting part of the text with the mouse is not a request to copy everything
    if (String(window.getSelection?.() ?? '').length > 0) return;
    const value = el.dataset.copy || el.textContent?.trim() || '';
    if (!value) return;
    event.preventDefault();
    event.stopPropagation();
    void copyText(value).then((ok) => {
        if (!ok) return;
        el.classList.add('is-copied');
        setTimeout(() => el.classList.remove('is-copied'), 1200);
        toast.success(t('Copied: {value}', { value: value.length > 70 ? `…${value.slice(-68)}` : value }), { duration: 1800 });
      });
  };
  document.addEventListener('click', onClick, true);
  return () => document.removeEventListener('click', onClick, true);
}
