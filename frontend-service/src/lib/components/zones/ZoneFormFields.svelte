<script lang="ts">
  import { t } from '$lib/i18n';
  export let form: {
    name: string;
    code?: string;
    description?: string;
  };

  export const mode: "create" | "edit" | "delete" = "create";
</script>

<!-- =====================================================
     NAME
===================================================== -->
<div class="zone-form-field">
  <label for="zone-name">{t('Zone name')} <span aria-hidden="true">*</span></label>
  <input
    id="zone-name"
    class="zone-form-control"
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
  <label for="zone-code">{t('Zone code')} <span>{t('(optional)')}</span></label>
  <input
    id="zone-code"
    class="zone-form-control"
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

<div class="zone-form-note">
  <i class="bi bi-rocket" aria-hidden="true"></i>
  <div>
    <strong>{t('Next step:')}</strong>
    {t('You will be able to run a discovery probe to detect storage.')}
  </div>
</div>

<style>
  .zone-form-field {
    display: grid;
    gap: 7px;
  }

  .zone-form-field label {
    margin: 0;
    color: #1f2c48;
    font-size: var(--b2s-fs-md);
    font-weight: 720;
  }

  .zone-form-field label > span {
    color: #64748b;
    font-weight: 650;
  }

  .zone-form-control {
    width: 100%;
    min-height: 42px;
    border: 1px solid #c8d2e4;
    border-radius: var(--b2s-radius-md);
    background: #f8fbff;
    color: #1f2e4b;
    padding: 0 12px;
    font-size: var(--b2s-fs-md);
    outline: none;
    transition:
      border-color 0.16s ease,
      box-shadow 0.16s ease,
      background-color 0.16s ease;
  }

  .zone-form-control:focus {
    border-color: #88a9e5;
    background: #ffffff;
    box-shadow: 0 0 0 3px rgba(36, 101, 199, 0.14);
  }

  .zone-form-note {
    border: 1px solid #d7e1f0;
    border-radius: var(--b2s-radius-md);
    background: #f4f8ff;
    color: #304867;
    padding: 11px 12px;
    display: flex;
    align-items: flex-start;
    gap: 9px;
    font-size: var(--b2s-fs-md);
    font-weight: 620;
  }

  .zone-form-note > i {
    color: var(--b2s-topbar-bg, #111b3f);
    margin-top: 1px;
  }
</style>
