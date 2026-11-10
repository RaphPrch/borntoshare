<script lang="ts">
  import { t } from '$lib/i18n';
  import { NAMING_MODELS, exampleGroupName } from '$lib/utils/naming-templates';

  /** Ready-made naming models: one click puts the template in the field (it can be edited afterwards). */
  export let template = '';
  export let onPick: (template: string) => void = () => {};
  export let prefix = '';
  export let zone = '';
  export let disabled = false;
</script>

<div class="nm" role="group" aria-label={t('Naming models')}>
  {#each NAMING_MODELS as model (model.key)}
    <button type="button" class="nm__item" class:is-on={template.trim() === model.template} {disabled} on:click={() => onPick(model.template)}>
      <b>{model.label()}</b>
      <code>{exampleGroupName(model.template, { prefix, zone })}</code>
    </button>
  {/each}
</div>

<style>
  .nm {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
  }

  .nm__item {
    display: grid;
    gap: 4px;
    padding: 10px 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    text-align: left;
    font: inherit;
    cursor: pointer;
    transition: border-color var(--b2s-motion-fast), background var(--b2s-motion-fast);
  }

  .nm__item:hover:not(:disabled) {
    border-color: var(--b2s-color-border-strong);
  }

  .nm__item.is-on {
    border-color: var(--b2s-accent-strong);
    background: var(--b2s-accent-soft);
  }

  .nm__item:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .nm__item b {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text);
  }

  .nm__item code {
    font-family: var(--b2s-font-mono);
    font-size: 11px;
    color: var(--b2s-color-text-muted);
    overflow-wrap: anywhere;
  }
</style>
