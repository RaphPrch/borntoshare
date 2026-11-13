<script lang="ts">
  import { t } from '$lib/i18n';

  interface Props {
    form: {
    name: string;
    code?: string;
    description?: string;
  };
    mode?: "create" | "edit" | "delete";
  }

  let { form = $bindable(), mode = "create" }: Props = $props();
</script>

<!-- =====================================================
     NAME
===================================================== -->
<div class="zone-form-field">
  <label class="b2s-form-label" for="zone-name">{t('Zone name')} <span class="req" aria-hidden="true">*</span></label>
  <input
    id="zone-name"
    class="b2s-input"
    bind:value={form.name}
    placeholder={t('Enter a zone name')}
    required
    autocomplete="off"
  />
</div>

<!-- =====================================================
     CODE
===================================================== -->
<div class="zone-form-field">
  <label class="b2s-form-label" for="zone-code">{t('Zone code')} <span>{t('(optional)')}</span></label>
  <input
    id="zone-code"
    class="b2s-input"
    bind:value={form.code}
    placeholder={t('Governance')}
    autocomplete="off"
  />
</div>

<div class="zone-form-note">
  <i class="bi bi-lightbulb" aria-hidden="true"></i>
  <div>
    {t('You can configure provisioning OU and naming policy from zone governance settings.')}
  </div>
</div>

{#if mode === 'create'}
<div class="zone-form-note">
  <i class="bi bi-rocket" aria-hidden="true"></i>
  <div>
    <strong>{t('Next step:')}</strong>
    {t('You will be able to run a discovery probe to detect storage.')}
  </div>
</div>
{/if}

<style>
  /* Fields: shared .b2s-form-label / .b2s-input (same as the storage endpoint forms) */
  .zone-form-field {
    display: grid;
  }

  .zone-form-field :global(.b2s-form-label > span:not(.req)) {
    color: var(--b2s-color-text-muted);
    font-weight: 400;
  }

  .zone-form-note {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 10px 12px;
    border: 1px solid var(--b2s-color-info-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-info-soft);
    color: var(--b2s-color-text-strong);
    font-size: var(--b2s-fs-sm);
  }

  .zone-form-note > i {
    margin-top: 1px;
    color: var(--b2s-color-info-strong);
  }
</style>
