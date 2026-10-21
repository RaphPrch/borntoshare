<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import type { ProvisioningConfigurationModel } from './provisioning-policy.types';

  export let model: ProvisioningConfigurationModel;

  $: zoneScope = model.scope === 'zone';
  $: mode = model.inheritanceMode ?? (zoneScope ? 'override' : 'inherit');
  $: locked = model.scope === 'storage-endpoint' && Boolean(model.inheritanceModeLocked);
  $: editable = zoneScope ? true : Boolean(model.canEditOverrideFields) && !locked;

  const triggerSave = () => model.onSavePolicy?.();
  const changeOu = (event: Event) => {
    const target = event.currentTarget as HTMLInputElement | null;
    model.onChangeOrganizationalUnit?.(String(target?.value ?? ''));
  };
  const changeNaming = (event: Event) => {
    const target = event.currentTarget as HTMLInputElement | null;
    model.onChangeNamingTemplate?.(String(target?.value ?? ''));
  };

  const tokenExamples = [
    { token: '{PREFIX}', meaning: t('Préfixe de convention (ex: B2S)') },
    { token: '{ROOTCODE}', meaning: t('Code du storage root (ex: finance_rw)') },
    { token: '{PERM}', meaning: t('Niveau de permission (ex: RX / RW)') }
  ];
</script>

<article class="provisioning-card">
  <header class="provisioning-card__header">
    <h2 class="provisioning-card__title">{t('Policy Configuration')}</h2>
  </header>

  <div class="provisioning-card__body">
    {#if model.scope === 'storage-endpoint'}
      <div class="provisioning-mode-group" role="radiogroup" aria-label={t('Provisioning mode')}>
        <section class={`provisioning-mode-option ${mode === 'inherit' ? 'provisioning-mode-option--active' : ''}`}>
          <label class="provisioning-mode-option__header">
            <input
              type="radio"
              name="endpoint-provisioning-mode"
              checked={mode === 'inherit'}
              on:change={() => model.onChangeInheritanceMode?.('inherit')}
              disabled={locked}
            />
            <span>{t('Inherit zone policy')}</span>
          </label>
          <p class="provisioning-mode-option__help">
            {t('Use policy defined in {value}', { value: (model.zoneLabel ?? 'selected zone') })}
          </p>
        </section>

        {#if !locked}
          <section class={`provisioning-mode-option ${mode === 'override' ? 'provisioning-mode-option--active' : ''}`}>
            <label class="provisioning-mode-option__header">
              <input
                type="radio"
                name="endpoint-provisioning-mode"
                checked={mode === 'override'}
                on:change={() => model.onChangeInheritanceMode?.('override')}
              />
              <span>{t('Endpoint override')}</span>
            </label>

            <div class="provisioning-mode-option__body">
              <label class="provisioning-field">
                <span class="provisioning-field__label">{t('Organizational Unit (OU)')}</span>
                <input
                  type="text"
                  value={model.organizationalUnit}
                  on:input={changeOu}
                  disabled={!editable}
                />
              </label>

              <label class="provisioning-field">
                <span class="provisioning-field__label">{t('Naming Template')}</span>
                <input
                  type="text"
                  value={model.namingTemplate}
                  on:input={changeNaming}
                  disabled={!editable}
                />
              </label>

              {#if model.tokensHint}
                <div class="provisioning-token-legend" role="note" aria-label={t('Token legend')}>
                  <div class="provisioning-field__help">{model.tokensHint}</div>
                  <ul class="provisioning-token-legend__list">
                    {#each tokenExamples as item}
                      <li>
                        <code>{item.token}</code>
                        <span>{item.meaning}</span>
                      </li>
                    {/each}
                  </ul>
                  <div class="provisioning-field__help">
                    {t('Exemple:')} <code>B2S_FINANCE_RW_RX</code> {t('avec template')} <code>{'{PREFIX}_{ROOTCODE}_{PERM}'}</code>
                  </div>
                </div>
              {/if}

              {#if model.showUseZoneValuesLink}
                <button
                  type="button"
                  class="provisioning-link"
                  on:click={() => model.onUseZoneValues?.()}
                  disabled={!editable}
                >
                  {t('Use zone values')}
                </button>
              {/if}
            </div>
          </section>
        {:else}
          <div class="provisioning-field__help">
            {t('This storage endpoint inherits provisioning policy from its zone.')}
          </div>
        {/if}
      </div>
    {:else}
      <div class="provisioning-form-stack">
        <label class="provisioning-field">
          <span class="provisioning-field__label">{t('Organizational Unit (OU)')}</span>
          <input
            type="text"
            value={model.organizationalUnit}
            on:input={changeOu}
            disabled={!model.onChangeOrganizationalUnit}
          />
        </label>

        <label class="provisioning-field">
          <span class="provisioning-field__label">{t('Naming Template')}</span>
          <input
            type="text"
            value={model.namingTemplate}
            on:input={changeNaming}
            readonly={!model.onChangeNamingTemplate}
          />
        </label>

        {#if model.tokensHint}
          <div class="provisioning-token-legend" role="note" aria-label={t('Token legend')}>
            <div class="provisioning-field__help">{model.tokensHint}</div>
            <ul class="provisioning-token-legend__list">
              {#each tokenExamples as item}
                <li>
                  <code>{item.token}</code>
                  <span>{item.meaning}</span>
                </li>
              {/each}
            </ul>
            <div class="provisioning-field__help">
              {t('Exemple:')} <code>B2S_FINANCE_RW_RX</code> {t('avec template')} <code>{'{PREFIX}_{ROOTCODE}_{PERM}'}</code>
            </div>
          </div>
        {/if}

        <div class="provisioning-actions">
          <EntityActionButton
            variant="primary"
            icon={model.savePolicyBusy ? 'bi-arrow-repeat' : 'bi-check2'}
            busy={model.savePolicyBusy}
            label={model.savePolicyBusy ? t('Saving…') : model.savePolicyLabel ?? t('Save policy')}
            className="provisioning-btn"
            disabled={model.savePolicyDisabled || model.savePolicyBusy}
            onClick={triggerSave}
          />
        </div>
      </div>
    {/if}
  </div>
</article>

<style>
  .provisioning-token-legend {
    display: grid;
    gap: 6px;
    padding: 10px 12px;
    border: 1px solid #dbe5f2;
    border-radius: var(--b2s-radius-md);
    background: #f8fbff;
  }

  .provisioning-token-legend__list {
    margin: 0;
    padding-left: 16px;
    display: grid;
    gap: 4px;
  }

  .provisioning-token-legend__list li {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }

  .provisioning-token-legend__list code {
    font-size: var(--b2s-fs-xs);
    color: #1e3a8a;
    background: #e8f0ff;
    border-radius: var(--b2s-radius-sm);
    padding: 1px 6px;
  }
</style>
