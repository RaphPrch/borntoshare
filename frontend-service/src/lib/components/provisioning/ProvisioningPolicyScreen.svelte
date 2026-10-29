<script lang="ts">
  import { onDestroy } from 'svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { t } from '$lib/i18n';
  import { previewRootGroups, type RootGroupsPreviewItem } from '$lib/api/naming-policies';
  import type { ProvisioningPolicyScreenProps } from './provisioning-policy.types';

  /**
   * Provisioning policy of a zone or a file server, in one card: where the AD groups are created (OU),
   * how they are named, and the groups that this gives for real storage roots (updated while typing).
   */
  export let scope: ProvisioningPolicyScreenProps['scope'];
  export let saveLabel: ProvisioningPolicyScreenProps['saveLabel'] = 'Save changes';
  export let configuration: ProvisioningPolicyScreenProps['configuration'];
  export let effective: ProvisioningPolicyScreenProps['effective'];
  export let onSave: ProvisioningPolicyScreenProps['onSave'] | null = null;
  export let saveDisabled: ProvisioningPolicyScreenProps['saveDisabled'] = false;
  export let saveBusy: ProvisioningPolicyScreenProps['saveBusy'] = false;
  export let errorMessage: ProvisioningPolicyScreenProps['errorMessage'] = null;
  export let showUnsaved: ProvisioningPolicyScreenProps['showUnsaved'] = false;
  /** Whose storage roots are previewed */
  export let previewTarget: { zone_id?: number | null; storage_endpoint_id?: number | null } = {};

  $: endpointScope = scope === 'storage-endpoint';
  $: mode = configuration.inheritanceMode ?? (endpointScope ? 'inherit' : 'override');
  $: locked = endpointScope && Boolean(configuration.inheritanceModeLocked);
  $: editing = endpointScope ? mode === 'override' && !locked && Boolean(configuration.canEditOverrideFields) : true;
  $: save = onSave ?? configuration.onSavePolicy ?? null;
  $: busy = Boolean(saveBusy || configuration.savePolicyBusy);
  $: disabled = Boolean(saveDisabled || configuration.savePolicyDisabled) || busy || !save;

  const value = (event: Event) => String((event.currentTarget as HTMLInputElement | null)?.value ?? '');

  // Groups for real storage roots, with the template being typed (an inherited endpoint previews the zone rule)
  let examples: RootGroupsPreviewItem[] = [];
  let existingGroups = 0;
  let examplesError: string | null = null;
  let examplesLoading = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let requestSeq = 0;

  $: draftTemplate = endpointScope ? (mode === 'override' ? configuration.namingTemplate : '') : configuration.namingTemplate;
  $: targetKey = `${previewTarget.zone_id ?? ''}|${previewTarget.storage_endpoint_id ?? ''}`;
  $: schedulePreview(targetKey, draftTemplate);

  function schedulePreview(key: string, template: string) {
    if (timer) clearTimeout(timer);
    if (key === '|') return;
    timer = setTimeout(() => void loadPreview(template), 350);
  }

  async function loadPreview(template: string) {
    const seq = ++requestSeq;
    examplesLoading = true;
    try {
      const result = await previewRootGroups(fetch, { ...previewTarget, template: String(template ?? '').trim() || null, limit: 3 });
      if (seq !== requestSeq) return;
      examples = result?.items ?? [];
      existingGroups = Number((result as { existing_groups?: number })?.existing_groups ?? 0);
      examplesError = null;
    } catch (error: unknown) {
      if (seq !== requestSeq) return;
      examplesError = error instanceof Error ? error.message : t('The template is not valid.');
    } finally {
      if (seq === requestSeq) examplesLoading = false;
    }
  }

  onDestroy(() => {
    if (timer) clearTimeout(timer);
  });

  const SOURCE_LABELS: Record<string, () => string> = {
    endpoint: () => t('Specific to this file server'),
    zone: () => t('Zone policy'),
    inherited: () => t('Inherited from the zone'),
    global: () => t('Global policy')
  };
</script>

<article class="b2s-panel pp" data-scope={scope}>
  <div class="b2s-panel__head">
    <h2>{t('Provisioning policy')}</h2>
    <StatusBadge compact showDot={false} variant={effective.sourceVariant === 'endpoint' ? 'warning' : 'info'}
      label={SOURCE_LABELS[effective.sourceVariant]?.() ?? effective.sourceLabel} />
  </div>

  <div class="b2s-panel__body pp__body">
    <p class="pp__intro">{t('Where BornToShare creates the AD access groups and how it names them.')}</p>

    {#if endpointScope}
      <div class="pp__modes" role="radiogroup" aria-label={t('Provisioning mode')}>
        <label class="pp__mode" class:is-active={mode === 'inherit'}>
          <input type="radio" name="pp-mode-{scope}" checked={mode === 'inherit'} disabled={locked}
            on:change={() => configuration.onChangeInheritanceMode?.('inherit')} />
          <span>
            <strong>{t('Inherit the zone policy')}</strong>
            <small>{configuration.zoneLabel ?? t('Zone of the file server')}</small>
          </span>
        </label>
        {#if !locked}
          <label class="pp__mode" class:is-active={mode === 'override'}>
            <input type="radio" name="pp-mode-{scope}" checked={mode === 'override'}
              on:change={() => configuration.onChangeInheritanceMode?.('override')} />
            <span>
              <strong>{t('Specific to this file server')}</strong>
              <small>{t('Own OU or naming template')}</small>
            </span>
          </label>
        {/if}
      </div>
    {/if}

    {#if editing}
      <div class="pp__fields">
        <label class="pp__field">
          <span class="b2s-form-label">{t('Organizational unit (OU) of the groups')}</span>
          <input class="b2s-form-control" type="text" value={configuration.organizationalUnit}
            placeholder="OU=Groups,DC=example,DC=org"
            readonly={!configuration.onChangeOrganizationalUnit}
            on:input={(e) => configuration.onChangeOrganizationalUnit?.(value(e))} />
        </label>
        <label class="pp__field">
          <span class="b2s-form-label">{t('Naming template')}</span>
          <input class="b2s-form-control pp__mono" type="text" value={configuration.namingTemplate}
            readonly={!configuration.onChangeNamingTemplate}
            on:input={(e) => configuration.onChangeNamingTemplate?.(value(e))} />
          <span class="b2s-form-hint">
            <code>{'{PREFIX}'}</code> {t('prefix')} · <code>{'{ROOTCODE}'}</code> {t('storage root path')} · <code>{'{PERM}'}</code> {t('RX (read) or RW (write)')}
          </span>
        </label>
        {#if configuration.showUseZoneValuesLink}
          <button type="button" class="pp__link" on:click={() => configuration.onUseZoneValues?.()}>
            {t('Use the zone values')}
          </button>
        {/if}
      </div>
    {:else}
      <dl class="b2s-kv">
        <dt>{t('OU of the groups')}</dt><dd class="pp__mono">{effective.effectiveOu || '—'}</dd>
        <dt>{t('Naming template')}</dt><dd class="pp__mono">{effective.effectiveNaming || '—'}</dd>
      </dl>
    {/if}

    <section class="pp__preview" aria-live="polite">
      <h3>{t('Groups for these storage roots')}</h3>
      {#if examplesError}
        <InlineAlert tone="error">{examplesError}</InlineAlert>
      {:else if examples.length === 0}
        <p class="pp__empty">{examplesLoading ? t('Loading…') : t('No storage root yet: the groups are named when the first access is approved.')}</p>
      {:else}
        <table class="b2s-table pp__table" class:is-loading={examplesLoading}>
          <thead>
            <tr><th>{t('Storage root')}</th><th>{t('Read group')}</th><th>{t('Write group')}</th></tr>
          </thead>
          <tbody>
            {#each examples as item (item.storage_root_id)}
              <tr>
                <td><strong>{item.name}</strong><small class="pp__mono">{item.root_path}</small></td>
                <td class="pp__mono">{item.read_group}</td>
                <td class="pp__mono">{item.write_group}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    {#if showUnsaved && existingGroups > 0}
      <InlineAlert tone="warning">
        {t('{count} AD group(s) already exist: they keep their name and OU. The new rule applies to the groups created from now on.', { count: existingGroups })}
      </InlineAlert>
    {/if}

    {#if errorMessage}
      <InlineAlert tone="error">{errorMessage}</InlineAlert>
    {/if}
  </div>

  {#if save}
    <footer class="pp__footer">
      {#if showUnsaved}<span class="pp__unsaved">{t('Unsaved changes')}</span>{/if}
      <button type="button" class="b2s-btn b2s-btn-primary" {disabled} on:click={() => save?.()}>
        <i class={`bi ${busy ? 'bi-hourglass-split' : 'bi-check2'}`} aria-hidden="true"></i>
        {busy ? t('Saving…') : saveLabel ?? t('Save changes')}
      </button>
    </footer>
  {/if}
</article>

<style>
  .pp__body {
    display: grid;
    gap: 16px;
  }

  .pp__intro {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .pp__modes {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .pp__mode {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-md);
    cursor: pointer;
  }

  .pp__mode.is-active {
    border-color: var(--b2s-topbar-bg);
    background: var(--b2s-color-primary-soft);
  }

  .pp__mode input {
    margin-top: 3px;
  }

  .pp__mode strong,
  .pp__mode small {
    display: block;
  }

  .pp__mode strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .pp__mode small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .pp__fields {
    display: grid;
    gap: 14px;
  }

  .pp__field {
    display: grid;
  }

  .pp__mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-sm);
    overflow-wrap: anywhere;
  }

  .pp__field code {
    font-family: var(--b2s-font-mono);
  }

  .pp__link {
    justify-self: start;
    padding: 0;
    border: none;
    background: none;
    color: var(--b2s-color-info);
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .pp__preview h3 {
    margin: 0 0 8px;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .pp__empty {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .pp__table td small {
    display: block;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .pp__table.is-loading {
    opacity: 0.6;
  }

  /* Zone: on the page surface, like the storage roots */
  .pp[data-scope='zone'] {
    border: 0;
    background: none;
    box-shadow: none;
  }

  .pp[data-scope='zone'] :global(.b2s-panel__head),
  .pp[data-scope='zone'] :global(.b2s-panel__body) {
    padding-inline: 0;
    border: 0;
  }

  .pp[data-scope='zone'] .pp__footer {
    justify-content: flex-start;
    padding-inline: 0;
    border-top: 0;
  }

  .pp__footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    padding: 14px 20px;
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .pp__unsaved {
    color: var(--b2s-color-warning-strong);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  @media (max-width: 720px) {
    .pp__modes {
      grid-template-columns: 1fr;
    }
  }
</style>
