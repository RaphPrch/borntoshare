import { recall, remember } from '$lib/utils/remember';

/**
 * `use:resizableColumns={'requests'}` on a <table>: each column title gets a handle on its right edge; dragging it
 * sets the width of the column (kept in this browser), a double-click gives it back its natural width.
 * Columns are known by their title text, so hiding one does not shift the widths of the others.
 */
export function resizableColumns(table: HTMLTableElement, key: string) {
  const store = `widths:${key}`;
  let widths = recall(store, { widths: {} as Record<string, number> }).widths as Record<string, number>;
  const handles: HTMLElement[] = [];
  let columns = 0;
  const nameOf = (th: HTMLElement) => (th.dataset.col || th.textContent || '').trim();

  function setup() {
    handles.splice(0).forEach((handle) => handle.remove());
    const heads = Array.from(table.querySelectorAll<HTMLTableCellElement>('thead th'));
    columns = heads.length;
    heads.forEach((th, index) => {
      const name = nameOf(th);
      if (!name || index === heads.length - 1) return; // the last column takes what is left
      if (widths[name]) th.style.width = `${widths[name]}px`;
      if (getComputedStyle(th).position === 'static') th.style.position = 'relative';
      const handle = document.createElement('span');
      handle.className = 'b2s-col-resize';
      handle.setAttribute('aria-hidden', 'true');
      handle.addEventListener('mousedown', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = th.getBoundingClientRect().width;
        document.body.classList.add('is-col-resizing');
        const move = (e: MouseEvent) => {
          th.style.width = `${Math.max(60, Math.round(startWidth + e.clientX - startX))}px`;
        };
        const up = () => {
          document.removeEventListener('mousemove', move);
          document.removeEventListener('mouseup', up);
          document.body.classList.remove('is-col-resizing');
          widths = { ...widths, [name]: Math.round(th.getBoundingClientRect().width) };
          remember(store, { widths });
        };
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
      });
      handle.addEventListener('click', (event) => event.stopPropagation());
      handle.addEventListener('dblclick', (event) => {
        event.stopPropagation();
        th.style.width = '';
        const { [name]: _gone, ...rest } = widths;
        widths = rest;
        remember(store, { widths });
      });
      th.appendChild(handle);
      handles.push(handle);
    });
  }

  setup();
  // Columns shown or hidden: the handles follow
  const observer = new MutationObserver(() => {
    if (table.querySelectorAll('thead th').length !== columns) setup();
  });
  const head = table.querySelector('thead');
  if (head) observer.observe(head, { childList: true, subtree: true });

  return {
    destroy() {
      observer.disconnect();
      handles.forEach((handle) => handle.remove());
    }
  };
}
