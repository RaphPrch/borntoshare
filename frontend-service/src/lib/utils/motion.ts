import { cubicOut } from 'svelte/easing';

/**
 * Motion of the application: three durations, one easing, and nothing at all when the person asked the system to
 * reduce motion (the global CSS rule in app.css covers CSS animations and Svelte transitions; `dur` covers the
 * JavaScript ones: counters, indicators).
 */
export const MOTION = { fast: 120, base: 200, slow: 320 } as const;

export function reducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

export const dur = (ms: number): number => (reducedMotion() ? 0 : ms);

/** A panel or a dialog that appears: fade, slight lift and scale (and the reverse when it leaves) */
type PopParams = { duration?: number; y?: number; scale?: number; delay?: number };
export function pop(_node: Element, { duration = MOTION.base as number, y = 8, scale = 0.97, delay = 0 }: PopParams = {}) {
  return {
    delay,
    duration: dur(duration),
    easing: cubicOut,
    css: (t: number, u: number) => `opacity:${t};transform:translateY(${u * y}px) scale(${scale + (1 - scale) * t})`
  };
}

/** Replays a CSS animation class on the node each time `key` changes (never on the first render) */
function replay(className: string) {
  return (node: HTMLElement, key: unknown) => {
    let last = key;
    const done = () => node.classList.remove(className);
    node.addEventListener('animationend', done);
    return {
      update(next: unknown) {
        if (next === last) return;
        last = next;
        if (reducedMotion()) return;
        node.classList.remove(className);
        void node.offsetWidth; // restart the animation
        node.classList.add(className);
      },
      destroy() {
        node.removeEventListener('animationend', done);
      }
    };
  };
}

/** The content of a workspace comes in when another entity is selected (no remount: state and data stay) */
export const enterOn = replay('b2s-enter');

/** A short green flash when a background job lands (pass a counter that grows on each success; 0 = nothing) */
export function flashOn(node: HTMLElement, tick: number) {
  const action = replay('b2s-flash')(node, tick);
  return { update: (next: number) => (next ? action.update(next) : undefined), destroy: action.destroy };
}

/** A counter badge that pulses once when its number goes up */
export function pulseOnIncrease(node: HTMLElement, count: number | null | undefined) {
  let last = Number(count ?? 0);
  const action = replay('b2s-pulse')(node, 0);
  let ticks = 0;
  return {
    update(next: number | null | undefined) {
      const value = Number(next ?? 0);
      if (value > last) action.update(++ticks);
      last = value;
    },
    destroy: action.destroy
  };
}

type IndicatorParams = { selector: string; key: unknown; axis?: 'x' | 'y' };

/**
 * A highlight that glides to the selected element (tab underline, selected row of a list).
 * The container gets the class `has-indicator` (its own selected style can step aside) and an element
 * `.b2s-indicator` placed under the element matching `selector`; it follows the layout (resize, expand, scroll).
 */
export function slideIndicator(container: HTMLElement, params: IndicatorParams) {
  let current = params;
  const indicator = document.createElement('span');
  indicator.className = `b2s-indicator b2s-indicator--${params.axis ?? 'x'}`;
  indicator.setAttribute('aria-hidden', 'true');
  container.prepend(indicator);
  container.classList.add('has-indicator');
  let frame = 0;
  let ready = false;

  function place() {
    frame = 0;
    const target = container.querySelector<HTMLElement>(current.selector);
    if (!target || target.getClientRects().length === 0) {
      indicator.style.opacity = '0';
      return;
    }
    const box = container.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    const left = rect.left - box.left + container.scrollLeft;
    const top = rect.top - box.top + container.scrollTop;
    indicator.style.opacity = '1';
    indicator.style.width = `${rect.width}px`;
    indicator.style.height = `${rect.height}px`;
    indicator.style.transform = `translate(${left}px, ${top}px)`;
    if (!ready) requestAnimationFrame(() => indicator.classList.add('is-ready'));
    ready = true;
  }
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(place);
  };
  const resize = new ResizeObserver(schedule);
  resize.observe(container);
  const mutations = new MutationObserver(schedule);
  mutations.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'aria-expanded'] });
  schedule();

  return {
    update(next: IndicatorParams) {
      current = next;
      schedule();
    },
    destroy() {
      resize.disconnect();
      mutations.disconnect();
      if (frame) cancelAnimationFrame(frame);
      indicator.remove();
      container.classList.remove('has-indicator');
    }
  };
}
