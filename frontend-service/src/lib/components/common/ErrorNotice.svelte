<script lang="ts">
  import type { AppError } from '$lib/core/errors';

  export let error: AppError | null = null;
  export let collapsible: boolean = true;

  let showDetails = false;

  if (!error) {
    // composant silencieux si pas d’erreur
  }

  function copyRequestId() {
    if (error?.requestId) {
      navigator.clipboard.writeText(error.requestId);
    }
  }
</script>

{#if error}
  <div class="error-notice error-{error.level}">
    <div class="error-header">
      <div class="error-title">{error.message}</div>

      {#if collapsible && error.hint}
        <button
          class="error-toggle"
          on:click={() => (showDetails = !showDetails)}
        >
          {showDetails ? 'Hide details' : 'View details'}
        </button>
      {/if}
    </div>

    <div class="error-message">{error.message}</div>

    {#if showDetails && error.hint}
      <div class="error-hint">
        {error.hint}
      </div>
    {/if}

    {#if error.requestId}
      <div class="error-meta">
        <span>Request ID :</span>
        <code>{error.requestId}</code>
        <button
          class="copy-btn"
          on:click={copyRequestId}
          title="Copier le Request ID"
        >
          Copier
        </button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .error-notice {
    border-radius: 6px;
    padding: 12px 14px;
    margin: 12px 0;
    font-size: 0.9rem;
  }

  .error-error {
    background: #fdecec;
    border: 1px solid #f5c2c7;
    color: #842029;
  }

  .error-warning {
    background: #fff3cd;
    border: 1px solid #ffecb5;
    color: #664d03;
  }

  .error-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }

  .error-title {
    font-weight: 600;
  }

  .error-toggle {
    background: none;
    border: none;
    color: inherit;
    font-size: 0.8rem;
    cursor: pointer;
    text-decoration: underline;
  }

  .error-message {
    margin-bottom: 6px;
  }

  .error-hint {
    font-size: 0.85rem;
    opacity: 0.9;
    margin-top: 4px;
  }

  .error-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    font-size: 0.8rem;
  }

  .error-meta code {
    background: rgba(0, 0, 0, 0.05);
    padding: 2px 4px;
    border-radius: 4px;
  }

  .copy-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.8rem;
    text-decoration: underline;
    color: inherit;
  }
</style>
