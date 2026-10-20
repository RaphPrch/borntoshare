<script lang="ts">
  import { t } from '$lib/i18n';
  export let error: { message?: string } | null;
  export let status: number;

  const isNotFound = status === 404;
  const isUnauthenticated = status === 401;
  const isForbidden = status === 403;
  const isServiceUnavailable = status === 503;

  const showDetails = import.meta.env.DEV;

  const title =
    isNotFound
      ? t('Page not found')
      : isUnauthenticated
      ? t('Session expired')
      : isForbidden
      ? t('Access denied')
      : isServiceUnavailable
      ? t('Service unavailable')
      : t('Unexpected error');

  const heading =
    isNotFound
      ? t('Page not found')
      : isUnauthenticated
      ? t('Your session has expired')
      : isForbidden
      ? t('Access denied')
      : isServiceUnavailable
      ? t('Service temporarily unavailable')
      : t('Something went wrong');

  const description =
    isNotFound
      ? t('The page you are looking for does not exist or has been moved.')
      : isUnauthenticated
      ? t('Please sign in again to continue.')
      : isForbidden
      ? t('You do not have permission to access this resource.')
      : isServiceUnavailable
      ? t('Authentication services are temporarily unavailable. Please try again later.')
      : t('An unexpected error occurred while rendering the application.');

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
        <a href="/login" class="btn-primary">{t('Sign in')}</a>
      {:else if isForbidden}
        <a href="/dashboard" class="btn-primary">{t('Back to dashboard')}</a>
      {:else if isServiceUnavailable}
        <button class="btn-primary" on:click={reload}>
          {t('Retry')}
        </button>
      {:else if isNotFound}
        <a href="/dashboard" class="btn-primary">{t('Go to dashboard')}</a>
      {/if}

      <a href="/dashboard" class="btn-secondary">{t('Home')}</a>
    </div>
  </div>
</div>

<style>
  .error-root {
    min-height: 100vh;
    background: radial-gradient(circle at top, #0b1530 0, #020617 35%, #020617 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem 1rem;
  }

  .error-card {
    max-width: 480px;
    width: 100%;
    background: #020617;
    border-radius: var(--b2s-radius-lg);
    padding: 2rem 1.8rem;
    box-shadow: 0 25px 60px rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.4);
    color: #e5e7eb;
  }

  .error-card h1 {
    margin: 0;
    font-size: 3rem;
    font-weight: 800;
    color: #38bdf8;
  }

  .error-card h2 {
    margin: 0.5rem 0 0.4rem;
    font-size: var(--b2s-fs-xl);
    font-weight: 600;
  }

  .error-card p {
    margin: 0 0 0.9rem;
    font-size: var(--b2s-fs-md);
    color: #9ca3af;
  }

  .error-message {
    background: #020617;
    border-radius: var(--b2s-radius-md);
    padding: 0.7rem 0.8rem;
    font-size: var(--b2s-fs-sm);
    color: #e5e7eb;
    border: 1px solid rgba(148, 163, 184, 0.4);
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

  .btn-primary,
  .btn-secondary {
    text-decoration: none;
    padding: 0.45rem 0.9rem;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-md);
    font-weight: 500;
    cursor: pointer;
  }

  .btn-primary {
    background: #2563eb;
    color: white;
    border: none;
  }

  .btn-primary:hover {
    background: #1d4ed8;
  }

  .btn-secondary {
    border: 1px solid #4b5563;
    color: #e5e7eb;
    background: transparent;
  }

  .btn-secondary:hover {
    background: #0b1120;
  }
</style>
