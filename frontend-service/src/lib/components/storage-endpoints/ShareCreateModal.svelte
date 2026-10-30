<script lang="ts">
  import { t } from '$lib/i18n';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { createStorageEndpointShare } from '$lib/api/storage-endpoints';
  import { toast } from '$lib/stores/toast';

  /** New share on a file server; its account must be a local administrator of the server. */
  export let open = false;
  export let endpointId: number;
  export let onClose: () => void = () => {};
  export let onCreated: () => void = () => {};

  let name = '';
  let path = '';
  let busy = false;
  let errorMessage = '';

  $: if (open) {
    name = '';
    path = '';
    errorMessage = '';
  }
  $: defaultPath = `C:\\Shares\\${name.trim() || '…'}`;

  async function submit(): Promise<void> {
    busy = true;
    errorMessage = '';
    try {
      await createStorageEndpointShare(fetch, endpointId, { name: name.trim(), path: path.trim() || undefined });
      toast.success(t('Share created.'));
      onClose();
      onCreated();
    } catch (error: any) {
      errorMessage = error?.message ?? t('Unable to create the share.');
    } finally {
      busy = false;
    }
  }
</script>

<AppModal {open} {onClose} title={t('Create a share')} subtitle={t('The account of this server must be a local administrator of it.')} iconClass="bi bi-folder-plus" closeOnBackdrop={false}>
  <div class="share-form">
    <label>
      {t('Share name')}
      <input class="b2s-input" bind:value={name} maxlength="80" placeholder="Finance" />
    </label>
    <label>
      {t('Local path on the server')}
      <input class="b2s-input" bind:value={path} maxlength="512" placeholder={defaultPath} />
      <small>{t('Created if it does not exist. Empty: {path}', { path: defaultPath })}</small>
    </label>
    {#if errorMessage}<InlineAlert tone="error">{errorMessage}</InlineAlert>{/if}
  </div>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-ghost" disabled={busy} on:click={onClose}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" disabled={busy || !name.trim()} on:click={submit}>
      {busy ? t('Creating…') : t('Create the share')}
    </button>
  </svelte:fragment>
</AppModal>

<style>
  .share-form { display: grid; gap: 14px; }
  .share-form label { display: grid; gap: 6px; font-weight: 500; }
  .share-form input { width: 100%; min-height: 40px; padding: 0 12px; border: 1px solid var(--b2s-color-border-strong); border-radius: 10px; font: inherit; font-weight: 400; }
  .share-form small { font-weight: 400; color: var(--b2s-color-text-muted); font-size: 12px; }
</style>
