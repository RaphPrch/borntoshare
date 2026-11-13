<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import NamingModelPicker from '$lib/components/provisioning/NamingModelPicker.svelte';
  import { NAMING_TOKENS, namingTokenHelp } from '$lib/utils/naming-templates';
  import ShowMore from '$lib/components/ui/ShowMore.svelte';
  import { onDestroy } from 'svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { t } from '$lib/i18n';
  import { previewRootGroups, type RootGroupsPreviewItem } from '$lib/api/naming-policies';
  import type { ProvisioningPolicyScreenProps } from './provisioning-policy.types';

  /**
   * Provisioning policy of a zone or a file server: the rule on the left (where the AD groups are created,
   * how they are named), the groups of its storage roots on the right, a page at a time and updated while
   * typing, with the groups that no longer follow the saved rule.
   */
  export let scope: ProvisioningPolicyScreenProps['scope'];
  /** The card of the AD groups of the folders (hidden on the server page: one place for them, the folder) */
  export let showGroups = true;
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
  /** Undo the unsaved changes */
  export let onDiscard: (() => void) | null = null;

  const PAGE = 25;
  const TOKENS = NAMING_TOKENS;

  $: endpointScope = scope === 'storage-endpoint';
  $: mode = configuration.inheritanceMode ?? (endpointScope ? 'inherit' : 'override');
  $: locked = endpointScope && Boolean(configuration.inheritanceModeLocked);
  $: editing = endpointScope ? mode === 'override' && !locked && Boolean(configuration.canEditOverrideFields) : true;
  $: save = onSave ?? configuration.onSavePolicy ?? null;
  $: busy = Boolean(saveBusy || configuration.savePolicyBusy);
  $: disabled = Boolean(saveDisabled || configuration.savePolicyDisabled) || busy || !save;

  const value = (event: Event) => String((event.currentTarget as HTMLInputElement | null)?.value ?? '');

  function insertToken(token: string) {
    const current = String(configuration.namingTemplate ?? '');
    configuration.onChangeNamingTemplate?.(current ? `${current}_${token}` : token);
  }

  // Groups of the storage roots, with the template being typed (an inherited endpoint previews the zone rule)
  let items: RootGroupsPreviewItem[] = [];
  let total = 0;
  let driftTotal = 0;
  let existingGroups = 0;
  let listError: string | null = null;
  let listLoading = false;
  let query = '';
  let driftOnly = false;
  let shown = PAGE;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let requestSeq = 0;

  $: draftTemplate = endpointScope ? (mode === 'override' ? configuration.namingTemplate : '') : configuration.namingTemplate;
  $: targetKey = `${previewTarget.zone_id ?? ''}|${previewTarget.storage_endpoint_id ?? ''}`;
  $: schedule(targetKey, draftTemplate, query, driftOnly, shown);

  function schedule(key: string, template: string, search: string, drift: boolean, limit: number) {
    if (timer) clearTimeout(timer);
    if (key === '|') return;
    timer = setTimeout(() => void load(template, search, drift, limit), 300);
  }

  async function load(template: string, search: string, drift: boolean, limit: number) {
    const seq = ++requestSeq;
    listLoading = true;
    try {
      // The page grows with « Show more »: one request for what is shown (at most 50 per call)
      const pages: RootGroupsPreviewItem[] = [];
      let result: Awaited<ReturnType<typeof previewRootGroups>> | null = null;
      for (let offset = 0; offset < limit; offset += 50) {
        result = await previewRootGroups(fetch, {
          ...previewTarget,
          template: String(template ?? '').trim() || null,
          limit: Math.min(50, limit - offset),
          offset,
          query: search.trim() || null,
          drift_only: drift
        });
        pages.push(...(result?.items ?? []));
        if ((result?.items ?? []).length < Math.min(50, limit - offset)) break;
      }
      if (seq !== requestSeq) return;
      items = pages;
      total = Number(result?.total ?? pages.length);
      driftTotal = Number(result?.drift_total ?? 0);
      existingGroups = Number(result?.existing_groups ?? 0);
      listError = null;
    } catch (error: unknown) {
      if (seq !== requestSeq) return;
      listError = error instanceof Error ? error.message : t('The template is not valid.');
    } finally {
      if (seq === requestSeq) listLoading = false;
    }
  }

  function setDriftOnly(next: boolean) {
    driftOnly = next;
    shown = PAGE;
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

<div class="pp" data-scope={scope}>
  <section class="pp__card" aria-label={t('Provisioning policy')}>
    <header class="pp__head">
      <h2>{endpointScope ? t('Rule of the file server') : t('Rule of the zone')}</h2>
      <StatusBadge compact showDot={false} variant={effective.sourceVariant === 'endpoint' ? 'warning' : 'info'}
        label={SOURCE_LABELS[effective.sourceVariant]?.() ?? effective.sourceLabel} />
    </header>
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
      <label class="pp__field">
        <span class="b2s-form-label">{t('Organizational unit (OU) of the groups')}</span>
        <input class="b2s-input pp__mono" type="text" value={configuration.organizationalUnit}
          placeholder="OU=Groups,DC=example,DC=org"
          readonly={!configuration.onChangeOrganizationalUnit}
          on:input={(e) => configuration.onChangeOrganizationalUnit?.(value(e))} />
      </label>
      <div class="pp__field">
        <label class="b2s-form-label" for="pp-template-{scope}">{t('Naming template')}</label>
        {#if configuration.onChangeNamingTemplate}
          <NamingModelPicker template={String(configuration.namingTemplate ?? '')} onPick={(model) => configuration.onChangeNamingTemplate?.(model)} />
        {/if}
        <input id="pp-template-{scope}" class="b2s-input pp__mono" type="text" value={configuration.namingTemplate}
          readonly={!configuration.onChangeNamingTemplate}
          on:input={(e) => configuration.onChangeNamingTemplate?.(value(e))} />
        {#if configuration.onChangeNamingTemplate}
          <div class="pp__tokens" role="group" aria-label={t('Insert a token')}>
            {#each TOKENS as token (token)}
              <button type="button" class="pp__token" on:click={() => insertToken(token)}>{token}</button>
            {/each}
          </div>
        {/if}
        <small class="pp__hint">
          {#each namingTokenHelp() as help, index (help.token)}{index ? ' · ' : ''}<code>{help.token}</code> {help.label}{/each}
        </small>
      </div>
      {#if configuration.showUseZoneValuesLink}
        <button type="button" class="pp__link" on:click={() => configuration.onUseZoneValues?.()}>
          {t('Use the zone values')}
        </button>
      {/if}
    {:else}
      <dl class="pp__kv">
        <div><dt>{t('OU of the groups')}</dt><dd class="pp__mono">{effective.effectiveOu || '—'}</dd></div>
        <div><dt>{t('Naming template')}</dt><dd class="pp__mono">{effective.effectiveNaming || '—'}</dd></div>
      </dl>
    {/if}

    {#if showUnsaved && existingGroups > 0}
      <InlineAlert tone="warning">
        {t('{count} AD group(s) already exist: they keep their name and OU. The new rule applies to the groups created from now on.', { count: existingGroups })}
      </InlineAlert>
    {/if}
    {#if errorMessage}
      <InlineAlert tone="error">{errorMessage}</InlineAlert>
    {/if}

    {#if save && !showUnsaved}
      <div class="pp__actions">
        <button type="button" class="b2s-btn b2s-btn-primary" {disabled} on:click={() => save?.()}>
          {busy ? t('Saving…') : saveLabel ?? t('Save changes')}
        </button>
      </div>
    {/if}
  </section>

  {#if showGroups}
  <section class="pp__card" aria-label={t('Groups of these storage roots')} aria-busy={listLoading}>
    <header class="pp__head">
      <h2>{t('Groups of these storage roots')}</h2>
      {#if driftTotal > 0}<span class="pp__pill pp__pill--warn">{t('{count} gap(s)', { count: driftTotal })}</span>{/if}
    </header>
    <div class="pp__tools">
      <input class="b2s-input" type="search" aria-label={t('Filter the folders')} placeholder={t('Filter the folders…')}
        bind:value={query} on:input={() => (shown = PAGE)} />
      <div class="pp__seg" role="group" aria-label={t('Filter by state')}>
        <button type="button" class:on={!driftOnly} aria-pressed={!driftOnly} on:click={() => setDriftOnly(false)}>{t('All')}{#if !driftOnly}<span>{total}</span>{/if}</button>
        <button type="button" class:on={driftOnly} aria-pressed={driftOnly} on:click={() => setDriftOnly(true)}>{t('Gaps')}<span>{driftTotal}</span></button>
      </div>
    </div>

    {#if listError}
      <InlineAlert tone="error">{listError}</InlineAlert>
    {:else if items.length === 0 && listLoading}
      <LoadingState skeleton="rows" rows={5}>{t('Loading…')}</LoadingState>
    {:else if items.length === 0}
      <p class="pp__empty">
        {driftOnly ? t('Every group follows the rule.') : query.trim() ? t('No folder matches this search.') : t('No storage root yet: the groups are named when the first access is approved.')}
      </p>
    {:else}
      <ul class="pp__list" class:is-loading={listLoading}>
        {#each items as item (item.storage_root_id)}
          <li>
            <span class="pp__root"><strong>{item.name}</strong><small class="pp__mono" title={item.root_path}>{item.root_path}</small></span>
            <span class="pp__groups">
              {#if item.drift}
                <span class="pp__mono" title={item.existing_read_group ?? item.existing_write_group}>{item.existing_read_group ?? item.existing_write_group}</span>
                <small title={item.read_group}>{t('Rule: {name}', { name: item.read_group })}</small>
              {:else}
                <span class="pp__mono" title={item.read_group}>{item.read_group}</span>
                <small class="pp__mono" title={item.write_group}>{item.write_group}</small>
              {/if}
            </span>
            <span class="pp__state">{#if item.drift}<span class="pp__pill pp__pill--warn">{t('Gap')}</span>{/if}</span>
          </li>
        {/each}
      </ul>
      <ShowMore shown={items.length} {total} page={PAGE} onMore={() => (shown += PAGE)} />
    {/if}
    <small class="pp__hint">{t('Existing groups are not renamed: the rule applies to the next folders. A gap is a group that no longer follows the saved rule.')}</small>
  </section>
  {/if}
</div>

{#if save && showUnsaved}
  <div class="pp__bar" role="status">
    <span>{t('Unsaved changes')}</span>
    {#if onDiscard}<button type="button" class="b2s-btn b2s-btn-secondary pp__bar-undo" on:click={() => onDiscard?.()}>{t('Cancel')}</button>{/if}
    <button type="button" class="b2s-btn b2s-btn-primary" {disabled} on:click={() => save?.()}>
      {busy ? t('Saving…') : saveLabel ?? t('Save changes')}
    </button>
  </div>
{/if}

<style>
  .pp {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 18px;
    align-items: start;
  }

  .pp__card {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    padding: 18px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
  }

  .pp__head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .pp__head h2 {
    margin: 0 auto 0 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .pp__intro,
  .pp__empty,
  .pp__hint {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .pp__hint code {
    font-family: var(--b2s-font-mono);
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

  .pp__field {
    display: grid;
    gap: 6px;
  }

  .pp__mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-sm);
    overflow-wrap: anywhere;
  }

  .pp__tokens {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .pp__token {
    padding: 2px 8px;
    border: 1px dashed var(--b2s-color-border-strong, var(--b2s-color-border));
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-muted, transparent);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    cursor: pointer;
  }

  .pp__token:hover {
    border-color: var(--b2s-color-text);
  }

  .pp__kv {
    display: grid;
    margin: 0;
  }

  .pp__kv div {
    display: grid;
    grid-template-columns: 150px minmax(0, 1fr);
    gap: 8px;
    padding: 8px 0;
    border-top: 1px solid var(--b2s-color-border);
  }

  .pp__kv div:first-child {
    border-top: 0;
  }

  .pp__kv dt {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .pp__kv dd {
    margin: 0;
  }

  .pp__link {
    justify-self: start;
    align-self: flex-start;
    padding: 0;
    border: none;
    background: none;
    color: var(--b2s-color-info);
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .pp__actions {
    display: flex;
  }

  .pp__tools {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .pp__tools .b2s-input {
    flex: 1;
    min-width: 0;
  }

  .pp__seg {
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface-muted, #e9ebf0);
  }

  .pp__seg button {
    border: 0;
    background: none;
    border-radius: var(--b2s-radius-sm);
    padding: 4px 10px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
    cursor: pointer;
  }

  .pp__seg button.on {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 600;
  }

  .pp__seg span {
    margin-left: 5px;
    opacity: 0.7;
  }

  .pp__list {
    margin: 0;
    padding: 0;
    list-style: none;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-md);
  }

  .pp__list.is-loading {
    opacity: 0.6;
  }

  .pp__list li {
    display: grid;
    grid-template-columns: minmax(0, 0.7fr) minmax(0, 1.5fr) auto;
    gap: 12px;
    align-items: center;
    padding: 9px 12px;
  }

  .pp__list li + li {
    border-top: 1px solid var(--b2s-color-border);
  }

  .pp__root,
  .pp__groups {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .pp__root strong {
    font-weight: 500;
  }

  .pp__root small,
  .pp__groups small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .pp__groups .pp__mono {
    font-size: var(--b2s-fs-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    overflow-wrap: normal;
  }

  .pp__state {
    text-align: right;
  }

  .pp__pill {
    display: inline-flex;
    padding: 2px 9px;
    border-radius: 99px;
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
    white-space: nowrap;
  }

  .pp__pill--warn {
    background: var(--b2s-color-warning-soft, #fdefd9);
    color: var(--b2s-color-warning-strong, #a85a00);
  }


  .pp__bar {
    position: sticky;
    bottom: 16px;
    z-index: 5;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 16px;
    padding: 10px 14px;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-topbar-bg, #0e1218);
    color: #fff;
    font-size: var(--b2s-fs-sm);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
  }

  .pp__bar .b2s-btn-primary {
    margin-left: auto;
  }

  .pp__bar-undo {
    margin-left: auto;
    background: transparent;
    color: #fff;
    border-color: rgba(255, 255, 255, 0.3);
  }

  .pp__bar-undo + .b2s-btn-primary {
    margin-left: 0;
  }
</style>
