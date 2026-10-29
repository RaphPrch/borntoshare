<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import {
    resetDatabase,
    saveDatabase,
    testDatabase,
    type DatabaseInfo,
    type DatabaseInput,
    type DatabaseTest
  } from '$lib/api/infrastructure';

  export let info: DatabaseInfo;
  export let onChanged: () => Promise<void> | void = () => {};

  let mode: 'fields' | 'dsn' = info.configured?.mode ?? info.running.mode ?? 'fields';
  let host = String(info.configured?.host ?? info.running.host ?? '');
  let port = Number(info.configured?.port ?? info.running.port ?? 3306);
  let name = String(info.configured?.name ?? info.running.name ?? '');
  let user = String(info.configured?.user ?? info.running.user ?? '');
  let loggingName = String(info.configured?.logging_name ?? info.running.logging_name ?? '');
  let password = '';
  let dsn = '';
  let loggingDsn = '';
  let showSecret = false;

  let testing = false;
  let saving = false;
  let result: DatabaseTest | null = null;
  let testedKey = '';
  let confirmReset = false;

  const setMode = (value: 'fields' | 'dsn') => {
    mode = value;
  };

  function input(): DatabaseInput {
    return mode === 'dsn'
      ? { mode, dsn: dsn.trim(), logging_dsn: loggingDsn.trim() || undefined }
      : { mode, host: host.trim(), port: Number(port), name: name.trim(), user: user.trim(), password: password || undefined, logging_name: loggingName.trim() || undefined };
  }

  $: formKey = JSON.stringify([mode, host, port, name, user, password, loggingName, dsn, loggingDsn]);
  // Saving needs a successful test of exactly these values
  $: canSave = !!result?.ok && testedKey === formKey && !saving;
  $: complete = mode === 'dsn' ? !!dsn.trim() : !!(host.trim() && name.trim() && user.trim() && port);
  $: sameAccount = host.trim() === info.running.host && user.trim() === info.running.user;

  async function runTest() {
    if (!complete || testing) return;
    testing = true;
    result = null;
    const key = formKey;
    try {
      result = await testDatabase(fetch, input());
      testedKey = key;
    } catch (e) {
      reportUiError(e, t('Database test failed.'), 'infrastructure.database.test');
    } finally {
      testing = false;
    }
  }

  async function save() {
    if (!canSave) return;
    saving = true;
    try {
      info = await saveDatabase(fetch, input());
      password = '';
      toast.success(t('Database connection saved. It applies at the next start of core-service.'));
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to save the database connection.'), 'infrastructure.database.save');
    } finally {
      saving = false;
    }
  }

  async function reset() {
    confirmReset = false;
    try {
      info = await resetDatabase(fetch);
      toast.success(t('Back to the .env settings at the next start.'));
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to reset the database connection.'), 'infrastructure.database.reset');
    }
  }
</script>

<div class="db-grid">
  <section class="panel">
    <header class="panel__head">
      <span class="panel__icon"><i class="bi bi-database-check" aria-hidden="true"></i></span>
      <div>
        <h3>{t('Connection in use')}</h3>
        <p>{info.running.source === 'runtime' ? t('Chosen on this page') : t('From the .env file')}</p>
      </div>
    </header>
    <dl class="facts">
      <dt>{t('Server')}</dt><dd class="mono">{info.running.host}:{info.running.port}</dd>
      <dt>{t('Database')}</dt><dd class="mono">{info.running.name}</dd>
      <dt>{t('Account')}</dt><dd class="mono">{info.running.user}</dd>
      <dt>{t('Audit database')}</dt><dd class="mono">{info.running.logging_name ?? '—'}</dd>
    </dl>

    {#if info.pending_restart && !info.configured}
      <div class="pending">
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>
        <div>
          <strong>{t('Restart required')}</strong>
          <span>{t('core-service goes back to the .env settings when it restarts.')}</span>
        </div>
      </div>
    {/if}

    {#if info.pending_restart && info.configured}
      <div class="pending">
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>
        <div>
          <strong>{t('Restart required')}</strong>
          <span>
            {t('Saved connection: {target}. It applies when core-service restarts.', {
              target: `${info.configured.host}:${info.configured.port}/${info.configured.name}`
            })}
          </span>
          {#if info.configured.updated_at}
            <small>{t('Saved by {who} on {when}', { who: info.configured.updated_by ?? '—', when: formatDateTime(info.configured.updated_at) })}</small>
          {/if}
        </div>
      </div>
    {/if}

    {#if info.configured}
      <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm reset" on:click={() => (confirmReset = true)}>
        <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
        {t('Back to the .env settings')}
      </button>
    {/if}
  </section>

  <section class="panel">
    <header class="panel__head">
      <span class="panel__icon"><i class="bi bi-sliders" aria-hidden="true"></i></span>
      <div>
        <h3>{t('Change the connection')}</h3>
        <p>{t('Tested before saving, applied at the next start of core-service.')}</p>
      </div>
    </header>

    {#if !info.runtime_dir_writable}
      <InlineAlert tone="warning">
        {t('The directory {dir} is not writable: mount it read-write on core-service to save a connection here.', { dir: info.runtime_dir })}
      </InlineAlert>
    {/if}

    <div class="segmented" role="tablist" aria-label={t('Connection type')}>
      <button type="button" role="tab" aria-selected={mode === 'fields'} class:is-active={mode === 'fields'} on:click={() => setMode('fields')}>
        <i class="bi bi-hdd-network" aria-hidden="true"></i>{t('Server')}
      </button>
      <button type="button" role="tab" aria-selected={mode === 'dsn'} class:is-active={mode === 'dsn'} on:click={() => setMode('dsn')}>
        <i class="bi bi-link-45deg" aria-hidden="true"></i>{t('Connection string (DSN)')}
      </button>
    </div>

    {#if mode === 'fields'}
      <div class="form-grid">
        <label class="f f--wide">
          <span>{t('Server name or IP')}</span>
          <input bind:value={host} placeholder="db01.example.com" autocomplete="off" />
        </label>
        <label class="f">
          <span>{t('Port')}</span>
          <input type="number" min="1" max="65535" bind:value={port} />
        </label>
        <label class="f">
          <span>{t('Database')}</span>
          <input bind:value={name} placeholder="borntoshare" autocomplete="off" />
        </label>
        <label class="f">
          <span>{t('Audit database')}</span>
          <input bind:value={loggingName} placeholder="borntoshare_logging" autocomplete="off" />
        </label>
        <label class="f">
          <span>{t('Account')}</span>
          <input bind:value={user} autocomplete="off" />
        </label>
        <label class="f">
          <span>{t('Password')}</span>
          <div class="b2s-input-with-action">
            <input
              type={showSecret ? 'text' : 'password'}
              bind:value={password}
              autocomplete="new-password"
              placeholder={sameAccount ? t('Unchanged') : ''}
            />
            <button type="button" class="b2s-input-action" aria-label={showSecret ? t('Hide password') : t('Show password')} on:click={() => (showSecret = !showSecret)}>
              <i class={`bi ${showSecret ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
          </div>
        </label>
      </div>
    {:else}
      <div class="form-grid">
        <label class="f f--full">
          <span>{t('Connection string')}</span>
          <div class="b2s-input-with-action">
            <input
              type={showSecret ? 'text' : 'password'}
              bind:value={dsn}
              placeholder="mariadb+pymysql://user:password@db01.example.com:3306/borntoshare"
              autocomplete="off"
              spellcheck="false"
            />
            <button type="button" class="b2s-input-action" aria-label={showSecret ? t('Hide password') : t('Show password')} on:click={() => (showSecret = !showSecret)}>
              <i class={`bi ${showSecret ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
            </button>
          </div>
          <small>{t('Overrides the server fields. The password is part of the string.')}</small>
        </label>
        <label class="f f--full">
          <span>{t('Audit database string (optional)')}</span>
          <input
            type={showSecret ? 'text' : 'password'}
            bind:value={loggingDsn}
            placeholder="mariadb+pymysql://user:password@db01.example.com:3306/borntoshare_logging"
            autocomplete="off"
            spellcheck="false"
          />
        </label>
      </div>
    {/if}

    {#if result}
      <div class={`result ${result.ok ? 'is-ok' : 'is-err'}`} class:is-outdated={testedKey !== formKey}>
        <i class={`bi ${result.ok ? 'bi-check-circle-fill' : 'bi-x-circle-fill'}`} aria-hidden="true"></i>
        <div>
          <strong>{t(result.message)}</strong>
          {#if result.version}
            <span>{result.version} · {result.latency_ms} ms · {t('{n} tables', { n: result.tables ?? 0 })}</span>
          {/if}
          {#if result.missing_tables?.length}
            <span>{t('Missing tables: {tables}', { tables: result.missing_tables.join(', ') })}</span>
          {/if}
          {#if testedKey !== formKey}
            <small>{t('The settings changed since this test: test again.')}</small>
          {/if}
        </div>
      </div>
    {/if}

    <div class="actions">
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={runTest} disabled={!complete || testing}>
        <i class={`bi ${testing ? 'bi-hourglass-split' : 'bi-plug'}`} aria-hidden="true"></i>
        {testing ? t('Testing…') : t('Test the connection')}
      </button>
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={save} disabled={!canSave || !info.runtime_dir_writable}>
        <i class="bi bi-save" aria-hidden="true"></i>
        {saving ? t('Saving…') : t('Save for the next start')}
      </button>
    </div>
  </section>
</div>

<ConfirmActionModal
  open={confirmReset}
  severity="warning"
  title={t('Back to the .env settings')}
  subtitle={t('The connection saved on this page is removed. core-service uses the .env settings at its next start.')}
  confirmLabel={t('Remove')}
  onConfirm={reset}
  onClose={() => (confirmReset = false)}
/>

<style>
  .db-grid {
    display: grid;
    grid-template-columns: minmax(260px, 0.8fr) minmax(0, 1.4fr);
    gap: 14px;
    align-items: start;
  }

  .panel {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    padding: 16px 18px;
    display: grid;
    gap: 14px;
  }

  .panel__head {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .panel__icon {
    width: 36px;
    height: 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-primary-soft);
    color: #1e3a8a;
    font-size: 1.1rem;
  }

  .panel__head h3 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    color: var(--b2s-color-heading);
  }

  .panel__head p {
    margin: 2px 0 0;
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .facts {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 14px;
    margin: 0;
    font-size: var(--b2s-fs-sm);
  }

  .facts dt {
    color: var(--b2s-color-text-muted);
  }

  .facts dd {
    margin: 0;
    color: var(--b2s-color-text);
    overflow-wrap: anywhere;
  }

  .mono {
    font-family: var(--b2s-font-mono);
  }

  .pending {
    display: flex;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-warning-soft);
    border: 1px solid var(--b2s-color-warning-border);
    color: #7c2d12;
    font-size: var(--b2s-fs-sm);
  }

  .pending div {
    display: grid;
    gap: 2px;
  }

  .pending small {
    color: #9a3412;
  }

  .reset {
    justify-self: start;
  }

  .segmented {
    display: inline-flex;
    padding: 3px;
    gap: 3px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-neutral-soft);
    justify-self: start;
  }

  .segmented button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 0;
    background: transparent;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
    cursor: pointer;
  }

  .segmented button.is-active {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-heading);
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
  }

  .form-grid {
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

  .f span {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text-strong);
  }

  .f small {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .f input {
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
    background: var(--b2s-color-surface);
  }

  .f input:focus {
    outline: 0;
    border-color: #8db5ff;
    box-shadow: 0 0 0 3px rgba(11, 99, 244, 0.12);
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
    opacity: 0.7;
  }

  .actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  @media (max-width: 1000px) {
    .db-grid {
      grid-template-columns: 1fr;
    }

    .form-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
