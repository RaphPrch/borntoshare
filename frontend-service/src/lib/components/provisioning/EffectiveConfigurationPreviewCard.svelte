<script lang="ts">
  import { t } from '$lib/i18n';
  import type { EffectiveProvisioningModel } from './provisioning-policy.types';

  export let model: EffectiveProvisioningModel;
  export let saveLabel = t('Save changes');
  export let onSave: (() => void) | undefined;
  export let saveDisabled = false;
  export let saveBusy = false;
  export let showSaveAction = true;

  $: sourceClass = `provisioning-source-badge provisioning-source-badge--${model.sourceVariant}`;
</script>

<article class="provisioning-card">
  <header class="provisioning-card__header">
    <h2 class="provisioning-card__title">{t('Effective Configuration Preview')}</h2>
  </header>

  <div class="provisioning-card__body">
    <div class="provisioning-kv">
      <section class="provisioning-kv__item">
        <span class="provisioning-kv__key">{t('Policy source')}</span>
        <span class={sourceClass}>{model.sourceLabel}</span>
      </section>

      <section class="provisioning-kv__item">
        <span class="provisioning-kv__key">{t('Effective OU')}</span>
        <strong class="provisioning-kv__value">{model.effectiveOu}</strong>
      </section>

      {#if model.effectivePrefix}
        <section class="provisioning-kv__item">
          <span class="provisioning-kv__key">{t('Group prefix')}</span>
          <span class="provisioning-chip">{model.effectivePrefix}</span>
        </section>
      {/if}

      <section class="provisioning-kv__item">
        <span class="provisioning-kv__key">{t('Effective naming')}</span>
        <span class="provisioning-chip">{model.effectiveNaming}</span>
      </section>

      {#if model.rootcodeStrategy || model.maxSamLength}
        <section class="provisioning-kv__item">
          <span class="provisioning-kv__key">{t('Naming rules')}</span>
          <div class="provisioning-chip-list">
            {#if model.rootcodeStrategy}
              <span class="provisioning-chip">{model.rootcodeStrategy}</span>
            {/if}
            {#if model.maxSamLength}
              <span class="provisioning-chip">{t('SAM max {maxSamLength}', { maxSamLength: model.maxSamLength })}</span>
            {/if}
          </div>
        </section>
      {/if}

      <section class="provisioning-kv__item">
        <span class="provisioning-kv__key">{t('Example groups')}</span>
        <div class="provisioning-chip-list">
          <span class="provisioning-chip">{model.exampleReadGroup}</span>
          <span class="provisioning-chip">{model.exampleWriteGroup}</span>
        </div>
      </section>
    </div>
  </div>

  {#if showSaveAction}
    <footer class="provisioning-card__footer">
      <button
        type="button"
        class="b2s-btn b2s-btn-primary provisioning-btn"
        on:click={() => onSave?.()}
        disabled={saveDisabled || saveBusy}
      >
        {saveBusy ? t('Saving…') : saveLabel}
      </button>
    </footer>
  {/if}
</article>
