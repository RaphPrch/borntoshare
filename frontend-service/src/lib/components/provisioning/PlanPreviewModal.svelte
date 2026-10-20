<script lang="ts">
  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';

  export let open = false;
  export let title = t('Preview changes');
  export let items: string[] = [];
  export let onClose: (() => void) | null = null;

  const close = () => onClose?.();
</script>

<AppModal {open} onClose={close} ariaLabelledby="plan-preview-title">
  <div class="b2s-confirm-head">
    <h3 id="plan-preview-title">{title}</h3>
  </div>
  <div class="b2s-confirm-body">
    {#if items.length === 0}
      <p>{t('No staged changes.')}</p>
    {:else}
      <ul>
        {#each items as item}
          <li>{item}</li>
        {/each}
      </ul>
    {/if}
  </div>
  <div class="b2s-confirm-actions">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={close}>{t('Close')}</button>
  </div>
</AppModal>
