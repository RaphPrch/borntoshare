<script lang="ts">
  import { t } from '$lib/i18n';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import type { DatabaseInfo } from '$lib/api/infrastructure';

  /**
   * The database connection in use, read only: the names come from .env, the passwords are podman secrets, both set
   * by the installation wizard. Changing the server is an operation (wizard, then make deploy), so that every part
   * of the platform (core, the 5S module, deploy and backup) keeps using the same one.
   */
  export let info: DatabaseInfo;

  // « GRANT SELECT, INSERT ON `borntoshare`.* TO `b2s_core`@`%` » → rights and target
  function readGrant(grant: string): { rights: string; target: string } {
    const match = /^GRANT (.+?) ON (.+?) TO /.exec(grant);
    return match ? { rights: match[1], target: match[2].replace(/`/g, '') } : { rights: grant, target: '' };
  }
  $: grants = (info.grants ?? []).map(readGrant);
</script>

<div class="db-grid">
  <section class="panel">
    <header class="panel__head">
      <span class="panel__icon" class:is-ok={info.ok} class:is-err={info.ok === false}><i class="bi bi-database-check" aria-hidden="true"></i></span>
      <div>
        <h3>{t('Connection in use')}</h3>
        <p>
          {#if info.ok === false && info.message}{t('Unreachable')}{:else if info.version}MariaDB {info.version} · {info.latency_ms} ms{/if}
        </p>
      </div>
    </header>
    <dl class="facts">
      <dt>{t('Server')}</dt><dd class="mono">{info.host}:{info.port}</dd>
      <dt>{t('Database')}</dt><dd class="mono">{info.name}{#if info.tables !== undefined} <small>· {t('{count} tables', { count: info.tables })}</small>{/if}</dd>
      <dt>{t('Audit database')}</dt><dd class="mono">{info.logging_name}{#if info.logging_tables !== undefined} <small>· {t('{count} tables', { count: info.logging_tables })}</small>{/if}</dd>
      <dt>{t('Application account')}</dt><dd class="mono">{info.user}</dd>
      <dt>{t('Migration account')}</dt><dd class="mono">{info.migrate_user}</dd>
      <dt>{t('Passwords')}</dt><dd>{info.password_from === 'secret' ? t('Podman secrets (never in .env)') : t('In .env: run make deploy to move them into podman secrets')}</dd>
    </dl>
    {#if info.ok === false && info.message}
      <InlineAlert tone="error">{info.message}</InlineAlert>
    {:else if info.missing_tables?.length}
      <InlineAlert tone="warning">{t('Tables missing: {tables}. Apply the SQL packs (make deploy).', { tables: info.missing_tables.join(', ') })}</InlineAlert>
    {/if}
  </section>

  <section class="panel">
    <header class="panel__head">
      <span class="panel__icon"><i class="bi bi-shield-lock" aria-hidden="true"></i></span>
      <div>
        <h3>{t('Rights of the application account')}</h3>
        <p>{t('Read and write only: the schema is changed by the migration account, during make deploy.')}</p>
      </div>
    </header>
    {#if info.schema_rights}
      <InlineAlert tone="warning">{t('This account can change the schema: its rights are wider than needed. Run the installation wizard again to give it only what it needs.')}</InlineAlert>
    {/if}
    {#if grants.length}
      <table class="rights">
        <thead><tr><th>{t('Scope')}</th><th>{t('Rights')}</th></tr></thead>
        <tbody>
          {#each grants as grant}
            <tr><td class="mono">{grant.target}</td><td>{grant.rights}</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <p class="hint">
      <i class="bi bi-info-circle" aria-hidden="true"></i>
      {t('To change the server, the databases or the accounts: the installation wizard (make wizard), then make deploy. The settings are in .env, the passwords in podman secrets.')}
    </p>
  </section>
</div>

<style>
  .db-grid {
    display: grid;
    grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1.3fr);
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
    color: var(--b2s-color-text-strong);
    font-size: 1.1rem;
  }

  .panel__icon.is-ok {
    background: var(--b2s-color-success-soft);
    color: var(--b2s-color-success-strong);
  }

  .panel__icon.is-err {
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
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

  .facts small {
    color: var(--b2s-color-text-muted);
    font-family: var(--b2s-font-sans);
  }

  .mono {
    font-family: var(--b2s-font-mono);
  }

  .rights {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--b2s-fs-sm);
  }

  .rights th {
    text-align: left;
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: var(--b2s-color-text-muted);
    padding: 0 10px 6px 0;
  }

  .rights td {
    padding: 8px 10px 8px 0;
    border-top: 1px solid var(--b2s-color-border-soft);
    vertical-align: top;
  }

  .hint {
    display: flex;
    gap: 8px;
    margin: 0;
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }
</style>
