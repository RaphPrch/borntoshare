<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import { timeAgo } from '$lib/utils/format';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { resolveCredentials } from '$lib/api/credentials';
  import { STATUS_VARIANT, statusLabel } from '$lib/utils/infrastructure';
  import {
    createSsoProvider,
    deleteSsoProvider,
    listSsoProviders,
    recordSsoStatus,
    testSsoProvider,
    updateSsoProvider,
    type RoleMapping,
    type SsoProvider,
    type SsoProviderInput,
    type SsoTestResult
  } from '$lib/api/infrastructure';

  let providers: SsoProvider[] = [];
  let roles: { code: string; label: string }[] = [];
  let loading = true;

  // ---- drawer
  let open = false;
  let editing: SsoProvider | null = null;
  let showErrors = false;
  let saving = false;
  let testing = false;
  let testResult: SsoTestResult | null = null;
  let testedKey = '';
  let secret = '';
  let showSecret = false;
  let publicClient = false;
  let claimPreset: 'realm' | 'client' | 'groups' | 'custom' = 'realm';
  let form: SsoProviderInput = blank();
  let removing: SsoProvider | null = null;
  let busyId: number | null = null;
  let origin = '';

  function blank(): SsoProviderInput {
    return {
      name: '',
      base_url: '',
      realm: '',
      client_id: 'borntoshare',
      scopes: 'openid profile email',
      username_claim: 'preferred_username',
      roles_claim: 'realm_access.roles',
      role_mapping: [{ value: '', role: 'platform_admin' }],
      default_role: null,
      link_existing_identities: true,
      button_label: '',
      verify_tls: true,
      is_enabled: true
    };
  }

  $: redirectUri = `${origin}/sso/callback`;
  $: formKey = JSON.stringify([form.base_url, form.realm, form.client_id, secret, publicClient, form.verify_tls]);
  $: urlError = form.base_url && !/^https?:\/\/[^\s/]+/.test(form.base_url.trim())
    ? t('An http:// or https:// URL is expected')
    : /\/realms\//.test(form.base_url)
      ? t('Without /realms/…: the realm has its own field')
      : null;
  $: valid =
    !!form.name.trim() && !!form.base_url.trim() && !urlError && !!form.realm.trim() && !!form.client_id.trim() &&
    (publicClient || !!secret || !!editing?.has_client_secret);
  $: if (claimPreset === 'realm') form.roles_claim = 'realm_access.roles';
  $: if (claimPreset === 'client') form.roles_claim = `resource_access.${form.client_id || 'client'}.roles`;
  $: if (claimPreset === 'groups') form.roles_claim = 'groups';

  async function load() {
    loading = true;
    try {
      const data = await listSsoProviders(fetch);
      providers = data.providers;
      roles = data.roles;
    } catch (e) {
      reportUiError(e, t('Unable to load the SSO providers.'), 'infrastructure.sso.load');
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    origin = window.location.origin;
    void load();
  });

  function presetOf(claim: string): typeof claimPreset {
    if (claim === 'realm_access.roles') return 'realm';
    if (claim === 'groups') return 'groups';
    if (/^resource_access\.[^.]+\.roles$/.test(claim)) return 'client';
    return 'custom';
  }

  function openAdd() {
    editing = null;
    form = blank();
    claimPreset = 'realm';
    secret = '';
    publicClient = false;
    testResult = null;
    showErrors = false;
    open = true;
  }

  function openEdit(provider: SsoProvider) {
    editing = provider;
    form = {
      name: provider.name,
      base_url: provider.base_url,
      realm: provider.realm,
      client_id: provider.client_id,
      scopes: provider.scopes,
      username_claim: provider.username_claim,
      roles_claim: provider.roles_claim,
      role_mapping: provider.role_mapping.length ? provider.role_mapping.map((m) => ({ ...m })) : [{ value: '', role: 'platform_admin' }],
      default_role: provider.default_role,
      link_existing_identities: provider.link_existing_identities,
      button_label: provider.button_label ?? '',
      verify_tls: provider.verify_tls,
      is_enabled: provider.is_enabled
    };
    claimPreset = presetOf(provider.roles_claim);
    secret = '';
    publicClient = !provider.has_client_secret;
    testResult = null;
    showErrors = false;
    open = true;
  }

  function addMapping() {
    form.role_mapping = [...form.role_mapping, { value: '', role: 'user' }];
  }

  function removeMapping(index: number) {
    form.role_mapping = form.role_mapping.filter((_, i) => i !== index);
  }

  /** The client secret goes to the secret broker; only its reference is saved */
  async function secretRef(): Promise<string | null> {
    if (publicClient || !secret) return null;
    const resolved = await resolveCredentials(
      fetch,
      { username: form.client_id.trim(), password: secret, secret_ref: null },
      { secretName: `sso/${form.realm.trim()}/${form.client_id.trim()}`, mode: 'create' }
    );
    return resolved.secret_ref ?? null;
  }

  async function runTest() {
    if (!form.base_url.trim() || !form.realm.trim() || !form.client_id.trim() || urlError) {
      showErrors = true;
      return;
    }
    testing = true;
    testResult = null;
    const key = formKey;
    try {
      const ref = await secretRef();
      testResult = await testSsoProvider(fetch, {
        provider_id: editing?.id,
        base_url: form.base_url.trim(),
        realm: form.realm.trim(),
        client_id: form.client_id.trim(),
        client_secret_ref: ref,
        verify_tls: form.verify_tls
      });
      testedKey = key;
      if (editing && !secret) {
        await recordSsoStatus(fetch, editing.id, testResult.ok ? 'healthy' : 'down', testResult.message);
      }
    } catch (e) {
      reportUiError(e, t('Keycloak test failed.'), 'infrastructure.sso.test');
    } finally {
      testing = false;
    }
  }

  async function save() {
    if (!valid) {
      showErrors = true;
      return;
    }
    saving = true;
    try {
      const body: SsoProviderInput = {
        ...form,
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        realm: form.realm.trim(),
        client_id: form.client_id.trim(),
        button_label: form.button_label?.trim() || null,
        role_mapping: form.role_mapping.filter((m) => m.value.trim()),
        client_secret_ref: await secretRef(),
        public_client: publicClient
      };
      const saved = editing ? await updateSsoProvider(fetch, editing.id, body) : await createSsoProvider(fetch, body);
      if (testResult && testedKey === formKey) {
        await recordSsoStatus(fetch, saved.id, testResult.ok ? 'healthy' : 'down', testResult.message);
      }
      toast.success(editing ? t('Keycloak server updated.') : t('Keycloak server added: its button appears on the sign-in page.'));
      open = false;
      secret = '';
      await load();
    } catch (e) {
      reportUiError(e, t('Unable to save the Keycloak server.'), 'infrastructure.sso.save');
    } finally {
      saving = false;
    }
  }

  async function quickTest(provider: SsoProvider) {
    busyId = provider.id;
    try {
      const result = await testSsoProvider(fetch, { provider_id: provider.id, verify_tls: provider.verify_tls });
      await recordSsoStatus(fetch, provider.id, result.ok ? 'healthy' : 'down', result.message);
      if (result.ok) toast.success(t('{name}: Keycloak answered, client accepted.', { name: provider.name }));
      else toast.error(`${provider.name}: ${t(result.message)}`);
      await load();
    } catch (e) {
      reportUiError(e, t('Keycloak test failed.'), 'infrastructure.sso.test');
    } finally {
      busyId = null;
    }
  }

  async function confirmRemove() {
    const provider = removing;
    removing = null;
    if (!provider) return;
    try {
      await deleteSsoProvider(fetch, provider.id);
      toast.success(t('Keycloak server removed.'));
      await load();
    } catch (e) {
      reportUiError(e, t('Unable to remove the Keycloak server.'), 'infrastructure.sso.remove');
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t('Copied.'));
    } catch {
      toast.error(t('Copy unavailable: select the text.'));
    }
  }

  function roleLabel(code: string | null | undefined): string {
    return roles.find((r) => r.code === code)?.label ?? code ?? '—';
  }
</script>

<div class="toolbar">
  <p>{t('Single sign-on with Keycloak (OpenID Connect). Each enabled server adds a button to the sign-in page.')}</p>
  <button type="button" class="b2s-btn b2s-btn-primary" on:click={openAdd}>
    <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add a Keycloak server')}
  </button>
</div>

{#if loading}
  <LoadingState />
{:else if providers.length === 0}
  <div class="empty">
    <i class="bi bi-key" aria-hidden="true"></i>
    <strong>{t('No Keycloak server')}</strong>
    <span>{t('Users sign in with their directory account or a local account.')}</span>
  </div>
{:else}
  <div class="cards">
    {#each providers as provider (provider.id)}
      <article class="card" class:is-off={!provider.is_enabled}>
        <header class="card__head">
          <span class={`card__icon is-${provider.status}`}><i class="bi bi-key" aria-hidden="true"></i></span>
          <div class="card__title">
            <strong>{provider.name}</strong>
            <span class="mono" title={provider.issuer_hint}>{provider.issuer_hint}</span>
          </div>
          {#if provider.is_enabled}
            <StatusBadge compact={true} status={provider.status} label={provider.status === 'unknown' ? t('Not tested') : statusLabel(provider.status)} variant={STATUS_VARIANT[provider.status]} />
          {:else}
            <StatusBadge compact={true} status="disabled" label={t('Disabled')} variant="disabled" />
          {/if}
        </header>
        {#if provider.last_message}
          <p class={`card__msg is-${provider.status}`}>{t(provider.last_message)}{#if provider.last_check_at} · {timeAgo(provider.last_check_at)}{/if}</p>
        {/if}
        <dl class="facts">
          <dt>{t('Client')}</dt><dd class="mono">{provider.client_id}{provider.has_client_secret ? '' : ` · ${t('public')}`}</dd>
          <dt>{t('Button')}</dt><dd>{provider.button_label || provider.name}</dd>
          <dt>{t('Roles from')}</dt><dd class="mono">{provider.roles_claim}</dd>
          <dt>{t('Directory accounts')}</dt><dd>{provider.link_existing_identities ? t('linked by user name') : t('not linked')}</dd>
        </dl>
        <div class="mappings">
          {#each provider.role_mapping as mapping (mapping.value)}
            <span class="map"><span class="mono">{mapping.value}</span><i class="bi bi-arrow-right" aria-hidden="true"></i>{roleLabel(mapping.role)}</span>
          {/each}
          <span class="map is-default">
            {t('Otherwise')}<i class="bi bi-arrow-right" aria-hidden="true"></i>{provider.default_role ? roleLabel(provider.default_role) : t('access refused')}
          </span>
        </div>
        <footer class="card__actions">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => quickTest(provider)} disabled={busyId === provider.id}>
            <i class={`bi ${busyId === provider.id ? 'bi-hourglass-split' : 'bi-plug'}`} aria-hidden="true"></i>{t('Test')}
          </button>
          <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => openEdit(provider)}>
            <i class="bi bi-pencil" aria-hidden="true"></i>{t('Edit')}
          </button>
          <button type="button" class="b2s-btn b2s-btn-danger-outline b2s-btn-sm card__remove" aria-label={t('Remove')} on:click={() => (removing = provider)}>
            <i class="bi bi-trash3" aria-hidden="true"></i>
          </button>
        </footer>
      </article>
    {/each}
  </div>
{/if}

<Drawer
  {open}
  size="lg"
  title={editing ? t('Edit the Keycloak server') : t('Add a Keycloak server')}
  subtitle={t('OpenID Connect, authorization code with PKCE')}
  iconClass="bi bi-key"
  ariaLabelledby="infra-sso-drawer-title"
  onClose={() => (open = false)}
>
  <div class="sections">
    <section class="sec">
      <h4>{t('Server')}</h4>
      <div class="grid">
        <label class="f f--full">
          <span>{t('Name')}</span>
          <input bind:value={form.name} placeholder="Keycloak" autocomplete="off" />
          {#if showErrors && !form.name.trim()}<FieldError>{t('Required')}</FieldError>{/if}
        </label>
        <label class="f f--wide">
          <span>{t('Server URL')}</span>
          <input bind:value={form.base_url} placeholder="https://sso.example.com" spellcheck="false" autocomplete="off" />
          {#if urlError}<FieldError>{urlError}</FieldError>{:else if showErrors && !form.base_url.trim()}<FieldError>{t('Required')}</FieldError>{/if}
        </label>
        <label class="f">
          <span>{t('Realm')}</span>
          <input bind:value={form.realm} placeholder="example" spellcheck="false" autocomplete="off" />
          {#if showErrors && !form.realm.trim()}<FieldError>{t('Required')}</FieldError>{/if}
        </label>
        <label class="f">
          <span>{t('Client ID')}</span>
          <input bind:value={form.client_id} spellcheck="false" autocomplete="off" />
        </label>
        <label class="f f--wide">
          <span>{t('Client secret')}</span>
          <div class="b2s-input-with-action">
            <input
              type={showSecret ? 'text' : 'password'}
              bind:value={secret}
              disabled={publicClient}
              autocomplete="new-password"
              placeholder={publicClient ? t('Public client: no secret') : editing?.has_client_secret ? t('Unchanged') : ''}
            />
            <button type="button" class="b2s-input-action" aria-label={showSecret ? t('Hide password') : t('Show password')} on:click={() => (showSecret = !showSecret)}>
              <i class={`bi ${showSecret ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
          </div>
          {#if showErrors && !publicClient && !secret && !editing?.has_client_secret}<FieldError>{t('Required')}</FieldError>{/if}
        </label>
        <div class="toggles f--full">
          <label class="toggle"><input type="checkbox" class="cap-switch" bind:checked={publicClient} /><span>{t('Public client (PKCE only, no secret)')}</span></label>
          <label class="toggle"><input type="checkbox" class="cap-switch" bind:checked={form.verify_tls} /><span>{t('Verify certificate')}</span></label>
        </div>
        <div class="redirect f--full">
          <span>{t('Redirect URI to declare on the Keycloak client')}</span>
          <div class="redirect__row">
            <code>{redirectUri}</code>
            <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => copy(redirectUri)}>
              <i class="bi bi-clipboard" aria-hidden="true"></i>{t('Copy')}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="sec">
      <h4>{t('Access to BornToShare')}</h4>
      <div class="grid">
        <label class="f f--wide">
          <span>{t('BornToShare roles come from')}</span>
          <select class="b2s-select" bind:value={claimPreset}>
            <option value="realm">{t('Realm roles')}</option>
            <option value="client">{t('Roles of this client')}</option>
            <option value="groups">{t('Groups (“groups” mapper)')}</option>
            <option value="custom">{t('Other claim')}</option>
          </select>
        </label>
        <label class="f">
          <span>{t('Claim')}</span>
          <input bind:value={form.roles_claim} disabled={claimPreset !== 'custom'} class="mono-input" spellcheck="false" />
        </label>
      </div>

      <div class="mapping">
        <div class="mapping__head">
          <span>{t('Keycloak value')}</span>
          <span></span>
          <span>{t('BornToShare role')}</span>
          <span></span>
        </div>
        {#each form.role_mapping as mapping, i (i)}
          <div class="mapping__row">
            <input bind:value={mapping.value} placeholder={claimPreset === 'groups' ? '/b2s-admins' : 'b2s-admins'} class="mono-input" spellcheck="false" aria-label={t('Keycloak value')} />
            <i class="bi bi-arrow-right" aria-hidden="true"></i>
            <select class="b2s-select" bind:value={mapping.role} aria-label={t('BornToShare role')}>
              {#each roles as role (role.code)}<option value={role.code}>{role.label}</option>{/each}
            </select>
            <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" aria-label={t('Remove')} on:click={() => removeMapping(i)}>
              <i class="bi bi-x-lg" aria-hidden="true"></i>
            </button>
          </div>
        {/each}
        <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm add-map" on:click={addMapping}>
          <i class="bi bi-plus" aria-hidden="true"></i>{t('Add a mapping')}
        </button>
      </div>

      <div class="grid">
        <label class="f f--wide">
          <span>{t('When no value matches')}</span>
          <select class="b2s-select" bind:value={form.default_role}>
            <option value={null}>{t('Refuse the sign-in')}</option>
            {#each roles as role (role.code)}<option value={role.code}>{t('Give the role {role}', { role: role.label })}</option>{/each}
          </select>
        </label>
        <div class="toggles f--full">
          <label class="toggle">
            <input type="checkbox" class="cap-switch" bind:checked={form.link_existing_identities} />
            <span>{t('Use the imported directory account with the same user name (its BornToShare roles apply)')}</span>
          </label>
        </div>
      </div>
    </section>

    <section class="sec">
      <h4>{t('Sign-in page')}</h4>
      <div class="grid">
        <label class="f f--wide">
          <span>{t('Button label')}</span>
          <input bind:value={form.button_label} placeholder={form.name || 'Keycloak'} autocomplete="off" />
        </label>
        <label class="f">
          <span>{t('User name claim')}</span>
          <input bind:value={form.username_claim} class="mono-input" spellcheck="false" />
        </label>
        <label class="f f--full">
          <span>{t('Scopes')}</span>
          <input bind:value={form.scopes} class="mono-input" spellcheck="false" />
        </label>
        <div class="toggles f--full">
          <label class="toggle"><input type="checkbox" class="cap-switch" bind:checked={form.is_enabled} /><span>{t('Enabled on the sign-in page')}</span></label>
        </div>
      </div>
    </section>

    {#if testResult}
      <div class={`result ${testResult.ok ? 'is-ok' : 'is-err'}`} class:is-outdated={testedKey !== formKey}>
        <i class={`bi ${testResult.ok ? 'bi-check-circle-fill' : 'bi-x-circle-fill'}`} aria-hidden="true"></i>
        <div>
          <strong>{t(testResult.message)}</strong>
          {#if testResult.issuer}<span class="mono">{testResult.issuer}</span>{/if}
          {#if testedKey !== formKey}<small>{t('The settings changed since this test: test again.')}</small>{/if}
        </div>
      </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="dfoot">
      <button type="button" class="b2s-btn b2s-btn-ghost" on:click={() => (open = false)}>{t('Cancel')}</button>
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={runTest} disabled={testing || saving}>
        <i class={`bi ${testing ? 'bi-hourglass-split' : 'bi-plug'}`} aria-hidden="true"></i>{testing ? t('Testing…') : t('Test')}
      </button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={save} disabled={saving || testing}>
        {saving ? t('Saving…') : editing ? t('Save changes') : t('Add the server')}
      </button>
    </div>
  </svelte:fragment>
</Drawer>

<ConfirmActionModal
  open={!!removing}
  title={t('Remove the Keycloak server')}
  subtitle={t('Its button leaves the sign-in page. Accounts created through it are disabled, their history stays.')}
  confirmLabel={t('Remove')}
  onConfirm={confirmRemove}
  onClose={() => (removing = null)}
/>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    justify-content: space-between;
    margin-bottom: 14px;
  }

  .toolbar p {
    margin: 0;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 36px 16px;
    border: 1px dashed var(--b2s-color-border-mid);
    border-radius: var(--b2s-radius-md);
    color: var(--b2s-color-text-muted);
    text-align: center;
  }

  .empty i {
    font-size: 1.8rem;
    color: var(--b2s-color-text-faint);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 12px;
  }

  .card {
    display: grid;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .card.is-off {
    opacity: 0.7;
  }

  .card__head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 10px;
    align-items: center;
  }

  .card__icon {
    width: 38px;
    height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-muted);
    font-size: 1.1rem;
  }

  .card__icon.is-healthy {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .card__icon.is-down {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .card__title {
    display: grid;
    min-width: 0;
  }

  .card__title strong {
    color: var(--b2s-color-heading);
  }

  .card__title span {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .card__msg {
    margin: 0;
    padding: 6px 10px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-soft);
  }

  .card__msg.is-down {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .card__msg.is-healthy {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .facts {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 6px 12px;
    margin: 0;
    font-size: var(--b2s-fs-xs);
  }

  .facts dt {
    color: var(--b2s-color-text-muted);
  }

  .facts dd {
    margin: 0;
    color: var(--b2s-color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mono,
  .mono-input {
    font-family: var(--b2s-font-mono);
  }

  .mappings {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .map {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 9px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-primary-soft);
    color: #3730a3;
    font-size: var(--b2s-fs-xs);
  }

  .map.is-default {
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-soft);
  }

  .card__actions {
    display: flex;
    gap: 6px;
    border-top: 1px solid var(--b2s-color-neutral-soft);
    padding-top: 10px;
  }

  .card__remove {
    margin-left: auto;
  }

  .sections {
    display: grid;
    gap: 16px;
  }

  .sec {
    display: grid;
    gap: 12px;
    padding: 14px 16px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
  }

  .sec h4 {
    margin: 0;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .f {
    display: grid;
    align-content: start;
    gap: 4px;
    min-width: 0;
  }

  .f--wide {
    grid-column: span 2;
  }

  .f--full {
    grid-column: 1 / -1;
  }

  .f > span,
  .redirect > span {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text-strong);
  }

  .f input,
  .mapping__row input {
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
  }

  .f input:disabled {
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text-muted);
  }

  .f input:focus,
  .mapping__row input:focus {
    outline: 0;
    border-color: #8db5ff;
    box-shadow: 0 0 0 3px rgba(11, 99, 244, 0.12);
  }

  .toggles {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
  }

  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-strong);
    cursor: pointer;
  }

  .redirect {
    display: grid;
    gap: 4px;
  }

  .redirect__row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 6px 6px 12px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    border: 1px dashed var(--b2s-color-border-mid);
  }

  .redirect__row code {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-xs);
  }

  .mapping {
    display: grid;
    gap: 6px;
  }

  .mapping__head,
  .mapping__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 20px minmax(0, 1fr) 36px;
    gap: 8px;
    align-items: center;
  }

  .mapping__head span {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text-strong);
  }

  .mapping__row i {
    color: var(--b2s-color-text-faint);
    text-align: center;
  }

  .add-map {
    justify-self: start;
  }

  .result {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
  }

  .result div {
    display: grid;
    gap: 2px;
  }

  .result.is-ok {
    background: var(--b2s-color-success-soft);
    border: 1px solid var(--b2s-color-success-border);
    color: #14532d;
  }

  .result.is-err {
    background: var(--b2s-color-danger-soft);
    border: 1px solid var(--b2s-color-danger-border);
    color: var(--b2s-color-danger-strong);
  }

  .result.is-outdated {
    opacity: 0.65;
  }

  .dfoot {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    width: 100%;
  }





</style>
