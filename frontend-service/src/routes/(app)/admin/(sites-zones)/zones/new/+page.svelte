<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from '$app/navigation';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { createZone, putZoneProvisioningPolicy } from '$lib/api/zones';
  import { putZoneNamingPolicy } from '$lib/api/naming-policies';
  import { toUiAppError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';

  /** Add a zone in one page: its name and code, then where and how its AD groups are created. */
  export let data: {
    sources: Array<{ id: number; name: string; ou: string; template: string }>;
    takenNames: string[];
    takenCodes: string[];
    globalTemplate: string;
    groupPrefix: string;
  };

  const TOKENS = ['{PREFIX}', '{ROOTCODE}', '{PERM}'];
  const ALLOWED = new Set(['PREFIX', 'ROOTCODE', 'PERM']);

  let name = '';
  let code = '';
  let codeEdited = false;
  let start = 'global';
  let ou = '';
  let template = data.globalTemplate;
  let creating = false;
  let createError = '';

  const codeFrom = (value: string) =>
    value.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 32);

  $: if (!codeEdited) code = codeFrom(name);

  function applyStart(value: string) {
    start = value;
    const source = data.sources.find((entry) => String(entry.id) === value);
    ou = source?.ou ?? '';
    template = source?.template || data.globalTemplate;
  }

  function insertToken(token: string) {
    template = template.trim() ? `${template.trim()}_${token}` : token;
  }

  $: nameTaken = data.takenNames.includes(name.trim().toLowerCase());
  $: codeTaken = Boolean(code.trim()) && data.takenCodes.includes(code.trim().toUpperCase());
  $: ouInvalid = Boolean(ou.trim()) && !/(^|,)\s*(OU|CN|DC)=/i.test(ou.trim());
  $: unknownTokens = [...template.matchAll(/\{([^}]*)\}/g)].map((match) => match[1]).filter((token) => !ALLOWED.has(token));
  $: templateInvalid = !template.trim() || unknownTokens.length > 0 || !template.includes('{ROOTCODE}');
  $: example = template
    .replaceAll('{PREFIX}', data.groupPrefix || 'B2S')
    .replaceAll('{ROOTCODE}', 'ACHATS')
    .replaceAll('{PERM}', 'RX')
    .toUpperCase();

  $: checks = [
    {
      title: t('Zone'),
      ok: Boolean(name.trim() && code.trim()) && !nameTaken && !codeTaken,
      detail: name.trim() ? `${name.trim()} · ${code || '—'}` : t('Name and code')
    },
    {
      title: t('OU of the groups'),
      ok: Boolean(ou.trim()) && !ouInvalid,
      optional: !ou.trim(),
      detail: ou.trim() ? (ouInvalid ? t('Not a distinguished name') : ou.trim()) : t('Directory default: can be set later')
    },
    {
      title: t('Naming'),
      ok: !templateInvalid,
      detail: templateInvalid ? t('The template needs {token}', { token: '{ROOTCODE}' }) : example
    }
  ];
  $: pendingReason =
    !name.trim() ? t('Enter the name of the zone.')
    : nameTaken ? t('A zone already has this name.')
    : !code.trim() ? t('Enter the code of the zone.')
    : codeTaken ? t('A zone already has this code.')
    : ouInvalid ? t('The OU must be a distinguished name, such as OU=Groups,DC=corp,DC=local.')
    : unknownTokens.length ? t('Unknown token: {token}', { token: `{${unknownTokens[0]}}` })
    : templateInvalid ? t('The template needs {token}', { token: '{ROOTCODE}' })
    : '';
  $: canCreate = !pendingReason && !creating;

  async function create() {
    if (!canCreate) return;
    creating = true;
    createError = '';
    let id = 0;
    try {
      ({ id } = await createZone(fetch, { name: name.trim(), code: code.trim() }));
    } catch (error) {
      createError = toUiAppError(error, t('Creation failed'), 'ui').message;
      creating = false;
      return;
    }
    // The zone exists: a failed rule is fixed from its Provisioning tab
    try {
      if (ou.trim()) {
        await putZoneProvisioningPolicy(fetch, id, { enabled: true, ou_strategy: 'identity_default', base_ou_dn: ou.trim(), static_ou_dn: null });
      }
      const custom = template.trim() !== data.globalTemplate;
      if (custom) await putZoneNamingPolicy(fetch, id, { override_enabled: true, template: template.trim() });
      toast.success(t('Zone created'));
      await goto(`/admin/zones/${id}`, { invalidateAll: true });
    } catch (error) {
      toast.error(t('Zone created, but its rule was not saved: {message}', { message: toUiAppError(error, t('Unknown error'), 'ui').message }));
      await goto(`/admin/zones/${id}?tab=provisioning`, { invalidateAll: true });
    }
  }
</script>

<svelte:head><title>{t('Add a zone')} · BornToShare</title></svelte:head>

<section class="b2s-page new-zone">
  <header class="head">
    <a class="crumb" href="/admin/zones"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Zones')}</a>
    <h1>{t('Add a zone')}</h1>
    <p>{t('A zone groups servers and sets where and how BornToShare creates their access groups.')}</p>
  </header>

  <div class="layout">
    <fieldset class="form" disabled={creating}>
      <section class="card">
        <h2>{t('Zone')}</h2>
        <div class="grid">
          <div class="field">
            <label for="zone-name">{t('Name')}</label>
            <input id="zone-name" class="b2s-input" bind:value={name} placeholder="Brest" />
            {#if nameTaken}<small class="field-error">{t('A zone already has this name.')}</small>{/if}
          </div>
          <div class="field">
            <label for="zone-code">{t('Code')}</label>
            <input id="zone-code" class="b2s-input mono" bind:value={code} on:input={() => (codeEdited = true)} placeholder="BREST" />
            {#if codeTaken}<small class="field-error">{t('A zone already has this code.')}</small>{:else}<small class="muted">{t('Proposed from the name.')}</small>{/if}
          </div>
        </div>
      </section>

      <section class="card">
        <h2>{t('Governance')}</h2>
        {#if data.sources.length}
          <div class="field">
            <span class="label">{t('Start from')}</span>
            <div class="seg" role="group" aria-label={t('Start from')}>
              <button type="button" class:on={start === 'global'} aria-pressed={start === 'global'} on:click={() => applyStart('global')}>{t('Global setting')}</button>
              {#each data.sources.slice(0, 4) as source (source.id)}
                <button type="button" class:on={start === String(source.id)} aria-pressed={start === String(source.id)} on:click={() => applyStart(String(source.id))}>{t('Zone {name}', { name: source.name })}</button>
              {/each}
            </div>
          </div>
        {/if}
        <div class="field">
          <label for="zone-ou">{t('OU of the access groups')}</label>
          <input id="zone-ou" class="b2s-input mono" bind:value={ou} placeholder="OU=B2S Groups,OU=BREST,DC=corp,DC=local" />
          {#if ouInvalid}<small class="field-error">{t('The OU must be a distinguished name, such as OU=Groups,DC=corp,DC=local.')}</small>{:else}<small class="muted">{t('Empty: the default OU of the directory of each server.')}</small>{/if}
        </div>
        <div class="field">
          <label for="zone-template">{t('Naming template')}</label>
          <input id="zone-template" class="b2s-input mono" bind:value={template} />
          <div class="tokens" role="group" aria-label={t('Insert a token')}>
            {#each TOKENS as token (token)}<button type="button" class="token" on:click={() => insertToken(token)}>{token}</button>{/each}
          </div>
          {#if templateInvalid}
            <small class="field-error">{unknownTokens.length ? t('Unknown token: {token}', { token: `{${unknownTokens[0]}}` }) : t('The template needs {token}', { token: '{ROOTCODE}' })}</small>
          {:else}
            <small class="muted">{t('Example: {name}', { name: example })}</small>
          {/if}
        </div>
      </section>
    </fieldset>

    <aside class="panel">
      <h2>{t('Configuration status')}</h2>
      <ul class="checks">
        {#each checks as check (check.title)}
          <li>
            <span class={`dot ${check.ok ? 'dot--ok' : check.optional ? '' : 'dot--warn'}`} aria-hidden="true">{#if check.ok}<i class="bi bi-check-lg"></i>{/if}</span>
            <span><strong>{check.title}</strong><small>{check.detail}</small></span>
          </li>
        {/each}
      </ul>
      <button type="button" class="b2s-btn b2s-btn-primary wide" disabled={!canCreate} on:click={create}>{creating ? t('Creating…') : t('Create the zone')}</button>
      {#if pendingReason}<small class="muted">{pendingReason}</small>{:else}<small class="muted">{t('Next: add its file servers or DFS namespaces.')}</small>{/if}
      {#if createError}<InlineAlert tone="error">{createError}</InlineAlert>{/if}
    </aside>
  </div>
</section>

<style>
  .new-zone { padding: var(--b2s-page-padding); }
  .head { margin-bottom: 20px; }
  .head h1 { margin: 4px 0 2px; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  .head p { margin: 0; color: var(--b2s-color-text-muted); }
  .crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); text-decoration: none; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px; max-width: 1240px; align-items: start; }
  .form { display: flex; flex-direction: column; gap: 14px; min-width: 0; margin: 0; padding: 0; border: 0; }
  .card, .panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); box-shadow: var(--b2s-shadow-sm); }
  .card { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; color: var(--b2s-color-heading); }
  .mono { font-family: var(--b2s-font-mono); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .field label, .label { font-size: var(--b2s-text-sm); font-weight: 500; }
  .field-error { color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow-wrap: anywhere; }
  .seg { display: inline-flex; flex-wrap: wrap; align-self: flex-start; gap: 2px; padding: 3px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-neutral-soft); }
  .seg button { padding: 5px 12px; border: 0; border-radius: var(--b2s-radius-sm); background: none; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); cursor: pointer; }
  .seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .tokens { display: flex; flex-wrap: wrap; gap: 6px; }
  .token { padding: 2px 8px; border: 1px dashed var(--b2s-color-border-mid, var(--b2s-color-border)); border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); cursor: pointer; }
  .token:hover { border-color: var(--b2s-color-text); }
  .panel { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 14px; padding: 18px; }
  .checks { display: grid; gap: 11px; margin: 0; padding: 0; list-style: none; }
  .checks li { display: grid; grid-template-columns: 18px 1fr; gap: 9px; font-size: var(--b2s-text-sm); }
  .checks strong, .checks small { display: block; }
  .checks small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow-wrap: anywhere; }
  .dot { display: grid; place-items: center; width: 18px; height: 18px; margin-top: 1px; border-radius: 50%; background: var(--b2s-color-neutral-soft); font-size: 11px; }
  .dot--ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .dot--warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .wide { width: 100%; justify-content: center; }
</style>
