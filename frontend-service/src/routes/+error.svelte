<script lang="ts">
  // SvelteKit gives an error page no props: the status and the error come from the page store
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';

  let status = $derived($page.status);
  let error = $derived($page.error as { message?: string } | null);

  let isNotFound = $derived(
    status === 404
  );
  let isUnauthenticated = $derived(
    status === 401
  );
  let isForbidden = $derived(
    status === 403
  );
  let isServiceUnavailable = $derived(
    status === 503
  );

  const showDetails = import.meta.env.DEV;

  let title = $derived(
    isNotFound
      ? t('Page not found')
      : isUnauthenticated
      ? t('Session expired')
      : isForbidden
      ? t('Access denied')
      : isServiceUnavailable
      ? t('Service unavailable')
      : t('Unexpected error')
  );

  let heading = $derived(
    isNotFound
      ? t('Page not found')
      : isUnauthenticated
      ? t('Your session has expired')
      : isForbidden
      ? t('Access denied')
      : isServiceUnavailable
      ? t('Service temporarily unavailable')
      : t('Something went wrong')
  );

  let description = $derived(
    isNotFound
      ? t('The page you are looking for does not exist or has been moved.')
      : isUnauthenticated
      ? t('Please sign in again to continue.')
      : isForbidden
      ? t('You do not have permission to access this resource.')
      : isServiceUnavailable
      ? t('Authentication services are temporarily unavailable. Please try again later.')
      : t('An unexpected error occurred while rendering the application.')
  );

  function reload() {
    location.reload();
  }
</script>

<svelte:head>
  <title>{t('{title} — Born To Share', { title })}</title>
</svelte:head>

<div class="error-root">
  <div class="error-card">
    <h1>{status}</h1>
    <h2>{heading}</h2>
    <p>{description}</p>

    {#if showDetails && error?.message}
      <pre class="error-message">
{error.message}
      </pre>
    {/if}

    <div class="error-actions">
      {#if isUnauthenticated}
        <a href="/login" class="b2s-btn b2s-btn-primary">{t('Sign in')}</a>
      {:else if isForbidden}
        <a href="/dashboard" class="b2s-btn b2s-btn-primary">{t('Back to dashboard')}</a>
      {:else if isServiceUnavailable}
        <button class="b2s-btn b2s-btn-primary" onclick={reload}>
          {t('Retry')}
        </button>
      {:else if isNotFound}
        <a href="/dashboard" class="b2s-btn b2s-btn-primary">{t('Go to dashboard')}</a>
      {/if}

      <a href="/dashboard" class="b2s-btn b2s-btn-secondary">{t('Home')}</a>
    </div>
  </div>
</div>

<style>
  .error-root {
    min-height: 100vh;
    background: var(--b2s-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem 1rem;
  }

  .error-card {
    max-width: 480px;
    width: 100%;
    background: var(--b2s-color-surface);
    border-radius: var(--b2s-radius-lg);
    padding: 2rem 1.8rem;
    box-shadow: var(--b2s-shadow-md);
    border: 1px solid var(--b2s-color-border-soft);
    color: var(--b2s-color-text);
  }

  .error-card h1 {
    margin: 0;
    font-size: 3rem;
    font-weight: 700;
    color: var(--b2s-accent);
  }

  .error-card h2 {
    margin: 0.5rem 0 0.4rem;
    font-size: var(--b2s-fs-xl);
    font-weight: 600;
  }

  .error-card p {
    margin: 0 0 0.9rem;
    font-size: var(--b2s-fs-md);
    color: var(--b2s-color-text-muted);
  }

  .error-message {
    background: var(--b2s-color-surface-soft);
    border-radius: var(--b2s-radius-md);
    padding: 0.7rem 0.8rem;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
    border: 1px solid var(--b2s-color-border-soft);
    max-height: 160px;
    overflow: auto;
    white-space: pre-wrap;
  }

  .error-actions {
    margin-top: 1.1rem;
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
</style>
