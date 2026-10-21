<script lang="ts">
  import { LOCALES, LOCALE_COOKIE, getLocale, t, type Locale } from '$lib/i18n';

  /** 'dark' on the navy top bar, 'light' on white pages (login) */
  export let tone: 'dark' | 'light' = 'dark';

  const current = getLocale();

  function choose(locale: Locale) {
    if (locale === current) return;
    document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; SameSite=Lax`;
    location.reload();
  }
</script>

<div class={`b2s-lang is-${tone}`} role="group" aria-label={t('Language')}>
  {#each LOCALES as locale}
    <button
      type="button"
      class:active={locale === current}
      aria-pressed={locale === current}
      lang={locale}
      title={locale === 'fr' ? 'Français' : 'English'}
      on:click={() => choose(locale)}
    >
      {locale.toUpperCase()}
    </button>
  {/each}
</div>

<style>
  .b2s-lang {
    display: inline-flex;
    padding: 2px;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid rgba(255, 255, 255, 0.28);
  }

  .b2s-lang.is-light {
    border-color: var(--b2s-color-border);
    background: var(--b2s-color-surface);
  }

  button {
    min-width: 34px;
    height: 26px;
    padding: 0 8px;
    border: 0;
    border-radius: var(--b2s-radius-pill);
    background: transparent;
    color: rgba(255, 255, 255, 0.78);
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
    cursor: pointer;
  }

  .is-light button {
    color: var(--b2s-color-text-muted);
  }

  button:hover {
    color: #ffffff;
  }

  .is-light button:hover {
    color: var(--b2s-color-text);
  }

  button.active {
    background: #ffffff;
    color: var(--b2s-topbar-bg);
  }

  .is-light button.active {
    background: var(--b2s-topbar-bg);
    color: #ffffff;
  }
</style>
