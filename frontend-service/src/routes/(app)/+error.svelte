<script lang="ts">
  // Errors of the signed-in pages keep the navigation: a forbidden page says so, with the way back
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  $: status = $page.status;
  $: forbidden = status === 403;
  $: title = forbidden ? t('Access denied') : status === 404 ? t('Page not found') : t('Something went wrong');
  $: text = forbidden
    ? t('This page is reserved to the administrators of the platform.')
    : status === 404
      ? t('The page you are looking for does not exist or has been moved.')
      : t('Try again in a moment. If it goes on, contact an administrator.');
</script>

<svelte:head><title>{title} · BornToShare</title></svelte:head>

<section class="denied" aria-labelledby="error-title">
  <i class={`bi ${forbidden ? 'bi-shield-lock' : 'bi-exclamation-circle'}`} aria-hidden="true"></i>
  <h1 id="error-title">{title}</h1>
  <p>{text}</p>
  <a class="b2s-btn b2s-btn-primary" href="/dashboard">{t('Back to the dashboard')}</a>
</section>

<style>
  .denied { display: flex; flex-direction: column; align-items: center; gap: 10px; max-width: 520px; margin: 12vh auto 0; padding: 32px; text-align: center; }
  .denied i { font-size: 34px; color: var(--b2s-color-text-muted); }
  h1 { margin: 0; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  p { margin: 0 0 8px; color: var(--b2s-color-text-muted); }
</style>
