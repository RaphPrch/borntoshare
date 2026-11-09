<script lang="ts">
  import { apiGetList } from '$lib/api/client';
  import { createIdentity, type CreateIdentityPayload } from '$lib/api/identity';
  import { listIdentitySources } from '$lib/api/identity-sources';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';

  /**
   * Add an identity in one screen: a person or a group found in the last reading of a directory (instant search,
   * the people already in BornToShare marked), or a local fallback account. A preview says what it will be able to do.
   */
  export let open = false;
  export let existing: Array<Record<string, any>> = [];
  export let onClose: () => void = () => {};
  export let onDone: (id: number | null) => void = () => {};

  type Kind = 'user' | 'group' | 'local';
  type Row = { id: number; username?: string; display_name?: string; name?: string; email?: string | null; upn?: string | null; dn?: string; external_id?: string | null; groups?: number; members?: number };
  let kind: Kind = 'user';
  let sources: Array<{ id: number; name: string }> = [];
  let sourceId = 0;
  let query = '';
  let results: Row[] = [];
  let searching = false;
  let picked: Row | null = null;
  let role: 'user' | 'platform_admin' = 'user';
  let saving = false;
  let error = '';
  let timer: ReturnType<typeof setTimeout> | null = null;
  let local = { username: '', display_name: '', email: '', password: '', change: true };

  $: if (open) init();
  let initialized = false;
  async function init() {
    if (initialized) return;
    initialized = true;
    const all = await listIdentitySources(fetch).catch(() => []);
    sources = all.filter((source: any) => ['ad', 'ldap'].includes(String(source?.type ?? '').toLowerCase()) && source?.is_active !== false)
      .map((source: any) => ({ id: Number(source.id), name: String(source.name) }));
    sourceId = sourceId || sources[0]?.id || 0;
    search();
  }
  function close() {
    initialized = false;
    query = '';
    results = [];
    picked = null;
    role = 'user';
    error = '';
    kind = 'user';
    local = { username: '', display_name: '', email: '', password: '', change: true };
    onClose();
  }

  function search() {
    if (timer) clearTimeout(timer);
    if (kind === 'local' || !sourceId) return;
    timer = setTimeout(async () => {
      searching = true;
      try {
        results = await apiGetList<Row>(fetch, `/identity-sources/${sourceId}/inventory`, { kind: kind === 'group' ? 'groups' : 'users', q: query.trim(), limit: 30 });
      } catch {
        results = [];
      } finally {
        searching = false;
      }
    }, query ? 220 : 0);
  }
  function setKind(next: Kind) {
    kind = next;
    picked = null;
    results = [];
    search();
  }

  const label = (row: Row) => String(row.display_name || row.name || row.username || '');
  const login = (row: Row) => String(row.username || row.name || '');
  const fold = (value: unknown) => String(value ?? '').toLowerCase();
  // Already in BornToShare: same login, or same directory object
  $: present = new Set(existing.flatMap((item) => [fold(item?.username), fold(item?.external_id), fold(item?.dn)].filter(Boolean)));
  const isPresent = (row: Row) => [login(row), row.external_id, row.dn].some((value) => value && present.has(fold(value)));
  function parts(text: string) {
    const at = query.trim() ? text.toLowerCase().indexOf(query.trim().toLowerCase()) : -1;
    return at < 0 ? { pre: text, hit: '', post: '' } : { pre: text.slice(0, at), hit: text.slice(at, at + query.trim().length), post: text.slice(at + query.trim().length) };
  }
  $: if (results.length && (!picked || !results.some((row) => row.id === picked?.id))) picked = results.find((row) => !isPresent(row)) ?? null;
  const initials = (text: string) => text.split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?';

  $: previewName = kind === 'local' ? local.display_name || local.username || t('New local account') : picked ? label(picked) : t('Choose in the list');
  $: previewMail = kind === 'local' ? local.email : picked?.email ?? '';
  $: blocked = kind === 'local' ? !(local.username.trim() && local.password.length >= 12) : !picked || isPresent(picked);
  $: can = role === 'platform_admin'
    ? [t('Everything a user does'), t('Declare servers, directories and folders'), t('Give the roles, validate every request')]
    : kind === 'group'
      ? [t('Every member signs in with their Windows account'), t('Every member can request access to a folder')]
      : [kind === 'local' ? t('Sign in with this login and password') : t('Sign in with their Windows account'), t('Request access to a folder'),
         previewMail ? t('Receive the decisions by e-mail') : t('See the decisions in BornToShare (no e-mail)')];

  async function save() {
    if (blocked || saving) return;
    saving = true;
    error = '';
    const payload: CreateIdentityPayload = kind === 'local'
      ? { identity_type: 'user', auth_source: 'local', username: local.username.trim(), display_name: local.display_name.trim() || local.username.trim(),
          email: local.email.trim() || null, temporary_password: local.password, require_password_change: local.change, application_role: role }
      : { identity_type: kind === 'group' ? 'group' : 'user', auth_source: 'ad', identity_source_id: sourceId, application_role: role,
          principal: { type: kind === 'group' ? 'group' : 'user', external_id: picked?.external_id || picked?.dn || login(picked!), dn: picked?.dn ?? null,
                       username: login(picked!), upn: picked?.upn ?? null, display_name: label(picked!), email: picked?.email ?? null } };
    try {
      const created: any = await createIdentity(fetch, payload);
      toast.success(t('{name} added.', { name: previewName }));
      const id = Number(created?.id ?? created?.data?.id ?? 0) || null;
      close();
      onDone(id);
    } catch (err: unknown) {
      error = (err as any)?.message ?? '';
      reportUiError(err, 'Unable to add the identity.', 'identity.add');
    } finally {
      saving = false;
    }
  }
</script>

<AppModal open={open} onClose={close} size="xl" title={t('Add an identity')} iconClass="bi bi-person-plus" closeOnBackdrop={false}>
  <div class="ia">
    <div class="ia__main">
      <div class="ia__kinds" role="tablist" aria-label={t('What are you adding?')}>
        <button type="button" role="tab" aria-selected={kind === 'user'} class:is-on={kind === 'user'} on:click={() => setKind('user')}>{t('A person')}</button>
        <button type="button" role="tab" aria-selected={kind === 'group'} class:is-on={kind === 'group'} on:click={() => setKind('group')}>{t('A directory group')}</button>
        <button type="button" role="tab" aria-selected={kind === 'local'} class:is-on={kind === 'local'} on:click={() => setKind('local')}>{t('A local account')}</button>
      </div>

      {#if kind !== 'local'}
        <div class="ia__searchrow">
          <label class="ia__search">
            <i class="bi bi-search" aria-hidden="true"></i>
            <!-- svelte-ignore a11y-autofocus -->
            <input autofocus bind:value={query} on:input={search} aria-label={t('Search the directory')}
              placeholder={kind === 'group' ? t('Name of the group…') : t('Name, login or e-mail…')} />
            {#if searching}<span class="ia__spin" aria-hidden="true"></span>{/if}
          </label>
          {#if sources.length > 1}
            <select class="b2s-input" bind:value={sourceId} on:change={search} aria-label={t('Directory')}>
              {#each sources as source (source.id)}<option value={source.id}>{source.name}</option>{/each}
            </select>
          {/if}
        </div>
        <div class="ia__results" role="listbox" aria-label={t('Results')}>
          {#each results as row (row.id)}
            {@const text = parts(label(row))}
            <button type="button" role="option" aria-selected={picked?.id === row.id} class:is-on={picked?.id === row.id} class:is-in={isPresent(row)} on:click={() => (picked = row)}>
              <span class="ia__av" class:is-group={kind === 'group'}>{kind === 'group' ? '' : initials(label(row))}{#if kind === 'group'}<i class="bi bi-people" aria-hidden="true"></i>{/if}</span>
              <span class="ia__who"><b>{text.pre}<mark>{text.hit}</mark>{text.post}</b>
                <small class="mono">{kind === 'group' ? t('{count} member(s)', { count: row.members ?? 0 }) : `${login(row)} · ${row.email || t('no e-mail')}`}</small></span>
              <span class="ia__state" class:is-in={isPresent(row)}>{isPresent(row) ? t('already present') : t('to add')}</span>
            </button>
          {:else}
            <p class="ia__empty">{searching ? t('Searching…') : sources.length ? t('Nobody matches in the last reading.') : t('No directory: declare one in Directories first.')}</p>
          {/each}
        </div>
        <small class="ia__hint">{t('Search in the last reading of the directory: someone just created in AD appears after the next synchronization.')}</small>
      {:else}
        <div class="ia__form">
          <label>{t('Login')}<input class="b2s-input mono" bind:value={local.username} autocomplete="off" placeholder="secours.admin" /></label>
          <label>{t('Display name')}<input class="b2s-input" bind:value={local.display_name} placeholder={t('Fallback administrator')} /></label>
          <label>{t('E-mail (optional)')}<input class="b2s-input" type="email" bind:value={local.email} /></label>
          <label>{t('Temporary password')}<input class="b2s-input" type="password" bind:value={local.password} autocomplete="new-password" />
            <small>{t('12 characters at least; keep it in a vault.')}</small></label>
          <label class="ia__check"><input type="checkbox" bind:checked={local.change} />{t('Change it at the first sign-in')}</label>
        </div>
      {/if}
    </div>

    <aside class="ia__preview" aria-label={t('Preview')}>
      <span class="ia__label">{t('Preview')}</span>
      <div class="ia__card">
        <span class="ia__big">{kind === 'group' ? '' : initials(previewName)}{#if kind === 'group'}<i class="bi bi-people" aria-hidden="true"></i>{/if}</span>
        <span class="ia__who"><b>{previewName}</b><small class="mono">{previewMail || (kind === 'group' ? t('directory group') : t('no e-mail'))}</small></span>
      </div>
      <fieldset class="ia__roles">
        <legend>{t('Role')}</legend>
        <button type="button" role="radio" aria-checked={role === 'user'} class:is-on={role === 'user'} on:click={() => (role = 'user')}>
          <b>{t('User')}</b><small>{t('Requests access, sees their folders. Becomes guardian when a folder names them.')}</small>
        </button>
        <button type="button" role="radio" aria-checked={role === 'platform_admin'} class:is-on={role === 'platform_admin'} on:click={() => (role = 'platform_admin')}>
          <b>{t('Administrator')}</b><small>{t('Manages the whole platform.')}</small>
        </button>
      </fieldset>
      <div class="ia__can">
        <b>{t('Will be able to')}</b>
        {#each can as line}<span><i class="bi bi-check2" aria-hidden="true"></i>{line}</span>{/each}
        {#if role === 'platform_admin' && kind === 'user'}
          <span class="ia__warn">{t('Prefer a directory group of administrators: leaving it in the directory removes the role.')}</span>
        {/if}
      </div>
      {#if error}<InlineAlert tone="error">{error}</InlineAlert>{/if}
      <button type="button" class="b2s-btn b2s-btn-primary ia__cta" disabled={blocked || saving} on:click={save}>
        {saving ? t('Adding…') : picked && isPresent(picked) && kind !== 'local' ? t('{name} is already in BornToShare', { name: previewName }) : t('Add {name}', { name: previewName })}
      </button>
    </aside>
  </div>
</AppModal>

<style>
  .ia { display: flex; gap: 0; margin: -20px -24px; min-height: 520px; }
  .ia__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; padding: 20px 24px; }
  .ia__kinds { align-self: flex-start; display: flex; gap: 2px; padding: 3px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .ia__kinds button { padding: 8px 14px; border: 0; border-radius: 10px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-size: var(--b2s-fs-sm); font-weight: 600; cursor: pointer; }
  .ia__kinds button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
  .ia__searchrow { display: flex; gap: 10px; }
  .ia__searchrow select { max-width: 200px; }
  .ia__search { flex: 1; display: flex; align-items: center; gap: 10px; height: 50px; padding: 0 16px; border: 2px solid var(--b2s-color-text); border-radius: 14px; }
  .ia__search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: 16px; color: var(--b2s-color-text); }
  .ia__spin { width: 14px; height: 14px; border: 2px solid var(--b2s-color-border); border-top-color: var(--b2s-color-info-strong); border-radius: 50%; animation: ia-spin 0.8s linear infinite; }
  @keyframes ia-spin { to { transform: rotate(360deg); } }
  .ia__results { display: flex; flex-direction: column; max-height: 360px; overflow: auto; border: 1px solid var(--b2s-color-border); border-radius: 14px; }
  .ia__results button { display: flex; gap: 12px; align-items: center; padding: 11px 16px; border: 0; border-top: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .ia__results button:first-child { border-top: 0; }
  .ia__results button:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .ia__results button.is-on { background: #e8eef8; box-shadow: inset 3px 0 0 var(--b2s-color-text); }
  .ia__av, .ia__big { flex: 0 0 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 12px; font-weight: 600; }
  .ia__av.is-group { border-radius: 9px; background: #efe7fb; color: #6b3fc4; }
  .is-in .ia__av { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ia__who { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .ia__who b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ia__who small { color: var(--b2s-color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  mark { background: #eef9d9; color: #1b2a05; border-radius: 3px; padding: 0 1px; }
  .ia__state { padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: #eef9d9; color: #1b2a05; font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .ia__state.is-in { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .ia__empty { margin: 0; padding: 18px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ia__hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ia__form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  .ia__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .ia__form small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 400; }
  .ia__form .ia__check { flex-direction: row; align-items: center; gap: 8px; grid-column: 1 / -1; font-weight: 400; }
  .ia__preview { flex: 0 0 340px; display: flex; flex-direction: column; gap: 14px; padding: 20px; background: var(--b2s-color-surface-soft, #f5f7fa); border-left: 1px solid var(--b2s-color-border); }
  .ia__label { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
  .ia__card { display: flex; align-items: center; gap: 12px; padding: 14px; border: 1px solid var(--b2s-color-border); border-radius: 14px; background: var(--b2s-color-surface); }
  .ia__big { flex-basis: 46px; height: 46px; font-size: 15px; background: linear-gradient(135deg, var(--b2s-color-info-soft), #c9d9fb); }
  .ia__roles { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; border: 0; }
  .ia__roles legend { margin-bottom: 8px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .ia__roles button { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface); color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .ia__roles button.is-on { border: 2px solid var(--b2s-color-text); padding: 11px; }
  .ia__roles small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ia__can { display: flex; flex-direction: column; gap: 6px; font-size: var(--b2s-fs-sm); }
  .ia__can span { display: flex; gap: 8px; }
  .ia__can i { color: var(--b2s-color-success-strong, #157a3c); }
  .ia__warn { padding: 10px 12px; border-radius: 10px; background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); }
  .ia__cta { margin-top: auto; justify-content: center; }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
