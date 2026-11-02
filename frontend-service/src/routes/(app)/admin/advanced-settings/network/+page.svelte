<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { saveDnsDomains, type DnsDomain } from '$lib/api/admin-advanced-settings';
  import { runProbeWithPolling } from '$lib/jobs/probe-runner';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';

  export let data: { configured: DnsDomain[]; proposed: DnsDomain[]; failed: boolean };

  type Row = { domain: string; servers: string };
  const toRows = (list: DnsDomain[]): Row[] => list.map((entry) => ({ domain: entry.domain, servers: entry.servers.join(', ') }));
  let rows: Row[] = toRows(data.configured);
  let saved = JSON.stringify(rows);
  let saving = false;

  const domainOk = (value: string) => /^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i.test(value.trim());
  const ipOk = (value: string) => /^(\d{1,3}\.){3}\d{1,3}$/.test(value) && value.split('.').every((part) => Number(part) <= 255);
  const servers = (row: Row) => row.servers.split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean);
  const rowError = (row: Row, index: number): string | null => {
    if (!domainOk(row.domain)) return t('Enter a domain such as corp.local.');
    if (rows.findIndex((other) => other.domain.trim().toLowerCase() === row.domain.trim().toLowerCase()) !== index) return t('This domain is listed twice.');
    const list = servers(row);
    if (!list.length || list.length > 3 || !list.every(ipOk)) return t('From 1 to 3 DNS servers, given by IP address.');
    return null;
  };
  $: errors = rows.map(rowError);
  $: dirty = JSON.stringify(rows) !== saved;
  $: canSave = dirty && !saving && errors.every((error) => !error);
  // The domains a directory proposes and that no line replaces
  $: proposedOnly = data.proposed.filter((entry) => !rows.some((row) => row.domain.trim().toLowerCase() === entry.domain));

  function add(entry?: DnsDomain) {
    rows = [...rows, entry ? { domain: entry.domain, servers: entry.servers.join(', ') } : { domain: '', servers: '' }];
  }

  async function save() {
    if (!canSave) return;
    saving = true;
    try {
      await saveDnsDomains(fetch, rows.map((row) => ({ domain: row.domain.trim().toLowerCase(), servers: servers(row) })));
      saved = JSON.stringify(rows);
      toast.success(t('DNS servers saved.'));
    } catch (error) {
      reportUiError(error, t('Unable to save the DNS servers.'), 'advanced_settings.network.save');
    } finally {
      saving = false;
    }
  }

  let testName = '';
  let testing = false;
  let testResult: { ok: boolean; text: string } | null = null;

  async function testResolution() {
    if (!testName.trim() || testing) return;
    testing = true;
    testResult = null;
    try {
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: { kind: 'network', protocol: 'dns', scope: 'read', target: { name: testName.trim() }, options: { timeout_sec: 10 }, context: { ui_origin: 'admin' } },
        intervalMs: 800,
        maxAttempts: 25
      });
      const details = result.result?.details ?? {};
      testResult = result.ok
        ? {
            ok: true,
            text: t('{name} → {fqdn} → {address} ({via})', {
              name: testName.trim(),
              fqdn: details.fqdn,
              address: details.address,
              via: details.via === 'system' ? t('usual resolver') : t('via {server}', { server: details.via })
            })
          }
        : { ok: false, text: t(String(result.errorMessage ?? result.result?.message ?? 'The name cannot be resolved.')) };
    } catch (error) {
      testResult = { ok: false, text: error instanceof Error ? error.message : t('The name cannot be resolved.') };
    } finally {
      testing = false;
    }
  }
</script>

<ConfigCard title={t('DNS of the Windows domains')} icon="bi-diagram-2"
  subtitle={t('The worker asks these DNS servers for the names of a domain, and for the short names (FILER01) returned by DFS and the directories. Other names go through the usual DNS. Applied from the next task, without restart.')}>
  {#if data.failed}<InlineAlert tone="warning">{t('The DNS settings cannot be read for now.')}</InlineAlert>{/if}

  <table class="dns">
    <thead><tr><th>{t('Domain')}</th><th>{t('DNS servers')}</th><th></th></tr></thead>
    <tbody>
      {#each rows as row, index}
        <tr>
          <td><input class="b2s-input mono" aria-label={t('Domain')} placeholder="corp.local" bind:value={row.domain} /></td>
          <td>
            <input class="b2s-input mono" aria-label={t('DNS servers')} placeholder="172.20.3.86" bind:value={row.servers} />
            {#if (row.domain || row.servers) && errors[index]}<small class="error">{errors[index]}</small>{/if}
          </td>
          <td class="end"><button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" aria-label={t('Remove {name}', { name: row.domain })} on:click={() => (rows = rows.filter((_, i) => i !== index))}>{t('Remove')}</button></td>
        </tr>
      {/each}
      {#each proposedOnly as entry (entry.domain)}
        <tr class="proposed">
          <td class="mono">{entry.domain}</td>
          <td><span class="mono">{entry.servers.join(', ')}</span> <span class="tag">{t('Proposed by the directory {name}', { name: entry.source ?? '' })}</span></td>
          <td class="end"><button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => add(entry)}>{t('Set')}</button></td>
        </tr>
      {/each}
      {#if !rows.length && !proposedOnly.length}
        <tr><td colspan="3" class="empty">{t('No domain yet: connect a directory, or add a domain.')}</td></tr>
      {/if}
    </tbody>
  </table>
  {#if proposedOnly.length}<p class="note">{t('A domain proposed by a directory is only asked for the names the usual DNS does not know. Set it to use it first.')}</p>{/if}
  <div class="actions">
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => add()}>{t('Add a domain')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={!canSave} on:click={save}>{saving ? t('Saving…') : t('Save')}</button>
  </div>
</ConfigCard>

<ConfigCard title={t('Test a name')} icon="bi-search" subtitle={t('Resolved by the worker, as for an SMB, LDAP or DFS access.')}>
  <div class="test">
    <input class="b2s-input mono" aria-label={t('Name to test')} placeholder="FILER01" bind:value={testName} on:keydown={(event) => event.key === 'Enter' && testResolution()} />
    <button type="button" class="b2s-btn b2s-btn-secondary" disabled={!testName.trim() || testing} on:click={testResolution}>{testing ? t('Resolving…') : t('Resolve from the worker')}</button>
  </div>
  {#if testResult}<InlineAlert tone={testResult.ok ? 'success' : 'error'}>{testResult.text}</InlineAlert>{/if}
  {#if dirty}<small class="muted">{t('Save first: the test uses the saved settings.')}</small>{/if}
</ConfigCard>

<style>
  .dns { width: 100%; border-collapse: collapse; }
  .dns th { padding: 8px 10px; text-align: left; font-size: var(--b2s-font-micro); font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; color: var(--b2s-color-text-muted); background: var(--b2s-color-surface-soft); }
  .dns td { padding: 8px 10px; border-top: 1px solid var(--b2s-color-border); vertical-align: top; }
  .dns .end { text-align: right; width: 110px; }
  .dns .mono, .mono { font-family: var(--b2s-font-mono); }
  .proposed td { color: var(--b2s-color-text-muted); }
  .tag { margin-left: 6px; padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: var(--b2s-font-micro); font-family: var(--b2s-font-sans); }
  .error { display: block; margin-top: 4px; color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
  .empty { color: var(--b2s-color-text-muted); text-align: center; }
  .actions { display: flex; justify-content: space-between; margin-top: 12px; }
  .test { display: flex; gap: 8px; margin-bottom: 10px; }
  .test .b2s-input { max-width: 320px; }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .note { margin: 8px 0 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
</style>
