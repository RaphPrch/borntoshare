<script lang="ts">
  import { t } from '$lib/i18n';

  interface Props {
    data: { username: string };
  }

  let { data }: Props = $props();

  let current = $state('');
  let next = $state('');
  let confirm = $state('');
  let busy = $state(false);
  let error = $state('');

  // The same rules as the installation wizard and the local accounts
  let rules = $derived([
    { label: t('12 characters or more'), ok: next.length >= 12 },
    { label: t('a lowercase and an uppercase letter'), ok: /[a-z]/.test(next) && /[A-Z]/.test(next) },
    { label: t('a digit and a special character'), ok: /\d/.test(next) && /[^A-Za-z0-9]/.test(next) },
    { label: t('not the sign-in name'), ok: !!next && !next.toLowerCase().includes(data.username.toLowerCase()) },
    { label: t('different from the temporary password'), ok: !!next && next !== current },
    { label: t('typed twice the same'), ok: !!next && next === confirm }
  ]);
  let ready = $derived(!!current && rules.every((rule) => rule.ok));

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    busy = true;
    error = '';
    try {
      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ current_password: current, new_password: next })
      });
      if (!response.ok) {
        error = response.status === 400 || response.status === 401
          ? t('The temporary password is not right.')
          : t('The password could not be changed. Try again in a moment.');
        return;
      }
      // A full load: the session no longer holds a temporary password
      window.location.assign('/dashboard');
    } catch {
      error = t('The password could not be changed. Try again in a moment.');
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{t('Change your password')} · BornToShare</title></svelte:head>

<main class="pw">
  <form class="pw__card" onsubmit={submit} autocomplete="off">
    <div class="pw__brand"><b aria-hidden="true">B</b><strong>BornToShare</strong></div>
    <h1>{t('Change your password')}</h1>
    <p class="pw__lead">{t('The password of {name} was set at the installation: choose your own before going further.', { name: data.username })}</p>

    <label class="pw__f" for="pw-current">{t('Temporary password')}
      <input id="pw-current" type="password" bind:value={current} autocomplete="current-password" required />
    </label>
    <label class="pw__f" for="pw-next">{t('New password')}
      <input id="pw-next" type="password" bind:value={next} autocomplete="new-password" required />
    </label>
    <label class="pw__f" for="pw-confirm">{t('Confirm the new password')}
      <input id="pw-confirm" type="password" bind:value={confirm} autocomplete="new-password" required />
    </label>

    <ul class="pw__rules" aria-label={t('Password rules')}>
      {#each rules as rule (rule.label)}
        <li class:ok={rule.ok}><i class={`bi ${rule.ok ? 'bi-check-circle-fill' : 'bi-circle'}`} aria-hidden="true"></i>{rule.label}</li>
      {/each}
    </ul>

    {#if error}<p class="pw__error" role="alert">{error}</p>{/if}

    <div class="pw__foot">
      <a href="/logout" data-sveltekit-reload>{t('Logout')}</a>
      <button type="submit" class="b2s-btn b2s-btn-primary" disabled={!ready || busy}>{busy ? t('Saving…') : t('Change the password')}</button>
    </div>
  </form>
</main>

<style>
  .pw { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; background: var(--b2s-color-page, #f5f6f8); }
  .pw__card { width: 100%; max-width: 440px; display: flex; flex-direction: column; gap: 16px; padding: 32px; border-radius: 18px; background: var(--b2s-color-surface); box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 12px 32px rgba(14, 18, 24, .08); }
  .pw__brand { display: flex; align-items: center; gap: 10px; }
  .pw__brand b { width: 36px; height: 36px; border-radius: 10px; background: var(--b2s-accent); color: #10140a; display: flex; align-items: center; justify-content: center; font-weight: 700; }
  h1 { margin: 8px 0 0; font-size: 22px; color: var(--b2s-color-heading); }
  .pw__lead { margin: 0; color: var(--b2s-color-text-muted); font-size: 14px; line-height: 1.5; }
  .pw__f { display: flex; flex-direction: column; gap: 6px; font-weight: 500; font-size: 13px; }
  .pw__f input { min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); font-size: 14px; }
  .pw__rules { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 13px; color: var(--b2s-color-text-muted); }
  .pw__rules li { display: flex; gap: 8px; align-items: center; }
  .pw__rules li.ok { color: var(--b2s-color-success, #1f7a43); }
  .pw__error { margin: 0; padding: 10px 12px; border-radius: 10px; background: var(--b2s-color-danger-soft, #fdecec); color: var(--b2s-color-danger, #b42318); font-size: 13px; }
  .pw__foot { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
  .pw__foot a { color: var(--b2s-color-text-muted); font-size: 13px; }
</style>
