<script lang="ts">
  import { t } from '$lib/i18n';
  import type { AppError } from '$lib/errors';
  import InlineAlert from './InlineAlert.svelte';

  export let error: AppError | null = null;
  export let collapsible: boolean = true;

  let showDetails = false;

  function copyRequestId() {
    if (error?.requestId) {
      navigator.clipboard.writeText(error.requestId);
    }
  }
</script>

{#if error}
  <InlineAlert tone={error.level === 'warning' ? 'warning' : 'error'} class="error-notice">
    <div>{error.message}</div>

    {#if error.hint && (!collapsible || showDetails)}
      <div class="error-hint">{error.hint}</div>
    {/if}

    {#if error.requestId}
      <div class="error-meta">
        <span>{t('Request ID :')}</span>
        <code>{error.requestId}</code>
        <button class="link-btn" type="button" on:click={copyRequestId} title={t('Copier le Request ID')}>
          {t('Copier')}
        </button>
      </div>
    {/if}

    <svelte:fragment slot="actions">
      {#if collapsible && error.hint}
        <button class="link-btn" type="button" on:click={() => (showDetails = !showDetails)}>
          {showDetails ? t('Hide details') : t('View details')}
        </button>
      {/if}
    </svelte:fragment>
  </InlineAlert>
{/if}

<style>
  :global(.error-notice) {
    margin: 12px 0;
  }

  .error-hint {
    margin-top: 4px;
    opacity: 0.9;
  }

  .error-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    font-size: var(--b2s-fs-xs);
  }

  .error-meta code {
    background: rgba(0, 0, 0, 0.05);
    padding: 2px 4px;
    border-radius: var(--b2s-radius-sm);
  }

  .link-btn {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-size: var(--b2s-fs-xs);
    text-decoration: underline;
    color: inherit;
  }
</style>
