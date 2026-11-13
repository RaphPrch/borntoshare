<script lang="ts">
  // Warns before the session closes for inactivity, and closes it at the end of the countdown.
  // Only the user's own actions count: the polling of open pages does not.
  import { onDestroy, onMount } from 'svelte';
  import { t } from '$lib/i18n';

  const WARNING_SECONDS = 120;
  const PING_EVERY_SECONDS = 60;
  // The server may have last seen the user one ping earlier: close just before it does
  const MARGIN_SECONDS = PING_EVERY_SECONDS;
  // Shared between tabs: working in one keeps the others open
  const STORAGE_KEY = 'b2s.session.lastActivity';
  const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel'] as const;

  let limitSeconds = $state(0);
  let remainingSeconds = $state(Number.POSITIVE_INFINITY);
  let lastActivity = Date.now();
  let lastPing = Date.now();
  let closing = $state(false);
  let timer: ReturnType<typeof setInterval> | undefined;

  let warning = $derived(limitSeconds > 0 && remainingSeconds <= WARNING_SECONDS);
  let minutes = $derived(Math.floor(Math.max(remainingSeconds, 0) / 60));
  let seconds = $derived(Math.max(remainingSeconds, 0) % 60);
  let time = $derived(`${minutes}:${String(seconds).padStart(2, '0')}`);

  function storeActivity(now: number): void {
    lastActivity = now;
    try {
      localStorage.setItem(STORAGE_KEY, String(now));
    } catch {
      // Without storage, each tab counts on its own
    }
  }

  function readActivity(): number {
    try {
      return Math.max(lastActivity, Number(localStorage.getItem(STORAGE_KEY)) || 0);
    } catch {
      return lastActivity;
    }
  }

  function currentPath(): string {
    return window.location.pathname + window.location.search;
  }

  function toLogin(reason?: 'idle'): void {
    const query = new URLSearchParams({ redirect: currentPath() });
    if (reason) query.set('reason', reason);
    window.location.assign(`/login?${query}`);
  }

  async function ping(): Promise<void> {
    lastPing = Date.now();
    try {
      const res = await fetch('/api/auth/session', { headers: { accept: 'application/json' } });
      // Ended by the server (maximum duration, revoked), not by this countdown
      if (res.status === 401) {
        toLogin();
        return;
      }
      if (!res.ok) return;
      const body = await res.json();
      limitSeconds = Number(body?.idle_seconds) || limitSeconds;
    } catch {
      // Service briefly unreachable: the next ping tries again
    }
  }

  async function closeSession(): Promise<void> {
    closing = true;
    if (timer) clearInterval(timer);
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => undefined);
    toLogin('idle');
  }

  function tick(): void {
    if (!limitSeconds || closing) return;
    const now = Date.now();
    lastActivity = readActivity();
    const allowed = Math.max(limitSeconds - MARGIN_SECONDS, WARNING_SECONDS);
    remainingSeconds = Math.ceil(allowed - (now - lastActivity) / 1000);
    if (remainingSeconds <= 0) {
      void closeSession();
      return;
    }
    if (lastActivity > lastPing && now - lastPing >= PING_EVERY_SECONDS * 1000) {
      void ping();
    }
  }

  function onActivity(): void {
    // During the countdown only the button answers: reaching it must not dismiss the banner
    if (warning) return;
    const now = Date.now();
    if (now - lastActivity >= 1000) storeActivity(now);
  }

  function stay(): void {
    storeActivity(Date.now());
    tick();
    void ping();
  }

  onMount(() => {
    storeActivity(Date.now());
    void ping();
    for (const name of ACTIVITY_EVENTS) window.addEventListener(name, onActivity, { passive: true });
    timer = setInterval(tick, 1000);
  });

  onDestroy(() => {
    if (typeof window === 'undefined') return;
    if (timer) clearInterval(timer);
    for (const name of ACTIVITY_EVENTS) window.removeEventListener(name, onActivity);
  });
</script>

{#if warning && !closing}
  <div class="idle-banner" role="alert">
    <i class="bi bi-hourglass-split" aria-hidden="true"></i>
    <span>
      {t('Your session will close in {time} because of inactivity.', { time })}
      <small>{t('Unsaved changes will be lost.')}</small>
    </span>
    <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" onclick={stay}>{t('Stay signed in')}</button>
  </div>
{/if}

<style>
  .idle-banner {
    position: fixed;
    top: 16px;
    left: 50%;
    z-index: 3000;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border: 1px solid var(--line2, #cdd2db);
    border-radius: var(--b2s-radius-md);
    background: #fdefd9;
    color: #0e1218;
    box-shadow: 0 8px 24px rgb(14 18 24 / 18%);
    font-size: 14px;
    white-space: nowrap;
  }

  .idle-banner i {
    color: #a85a00;
  }

  .idle-banner small {
    margin-left: 6px;
    color: #596273;
  }
</style>
