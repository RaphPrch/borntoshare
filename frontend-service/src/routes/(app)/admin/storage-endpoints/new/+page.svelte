<script lang="ts">
  import { tick } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { resolveCredentials } from '$lib/api/credentials';
  import { createStorageEndpoint } from '$lib/api/storage-endpoints';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { humanizeFileServerMessage } from '$lib/errors/file-server';
  import { notifyError, toUiAppError } from '$lib/errors';
  import { buildStorageEndpointConnectProbeRequest } from '$lib/jobs/probe-builders';
  import { parseStorageEndpointProbeRoots } from '$lib/jobs/storage-endpoint-probe';
  import { runProbeWithPolling, syncStorageRootDiscoveryForEndpoint } from '$lib/jobs/probe-runner';
  import { isValidHostname, isValidIPv4 } from '$lib/utils/host-validate';

  type Endpoint = { id: number; isDfs: boolean; name: string; host: string; zoneId: number; account: string; secretRef: string; identitySourceId: number | null };
  export let data: {
    zones: { id: number; name: string }[];
    endpoints: Endpoint[];
    sources: { id: number; name: string; domain: string }[];
    zoneId: number | null;
    kind: 'filer' | 'dfs';
  };
  type Namespace = { name: string; path: string; type: 'domain' | 'standalone'; root_targets: string[]; links: { path: string; targets: string[] }[]; error: string | null };

  // One page for both: a file server (its shares) or a DFS namespace (its folders and their targets)
  let kind: 'filer' | 'dfs' = data.kind;
  let namespaces: Namespace[] = [];
  let picked = new Set<string>();
  let dfsServer = '';
  type State = 'idle' | 'running' | 'ok' | 'warn' | 'failed';
  type Found = { address?: string; dialect?: string | null; netbios_name?: string | null; dns_name?: string | null; domain?: string | null };

  let host = '';
  let port = 445;
  let analysedHost = '';
  let analysis: State = 'idle';
  let analysisMessage = '';
  let found: Found = {};
  let zoneId: number | null = data.zoneId ?? (data.zones.length === 1 ? data.zones[0].id : null);
  let name = '';
  let autoName = '';
  let sourceId: number | null = null;

  // Account: taken from a server of the same zone, or typed
  let reuseFrom: number | null = null;
  let account = '';
  let password = '';
  let secretRef: string | null = null;
  let test: State = 'idle';
  let testMessage = '';
  let testedKey = '';
  let shares: string[] = [];
  let probeResult: any = null;

  let creating = false;
  let createError = '';

  const strip = (value: string) => value.trim().replace(/^\\\\|^\/\//, '').split(/[\\/]/)[0];
  $: cleanHost = strip(host);
  $: hostValid = isValidIPv4(cleanHost) || isValidHostname(cleanHost);
  $: if (analysedHost && cleanHost !== analysedHost) resetAnalysis();
  $: zoneServers = data.endpoints.filter((endpoint) => endpoint.zoneId === zoneId && endpoint.account && endpoint.secretRef);
  $: if (reuseFrom && !zoneServers.some((endpoint) => endpoint.id === reuseFrom)) reuseFrom = null;
  $: reused = zoneServers.find((endpoint) => endpoint.id === reuseFrom) ?? null;
  $: effectiveAccount = reused ? reused.account : account.trim();
  // The same server under another name (IP / short name / FQDN) is caught with what it announced
  const isIp = (value: string) => /^[0-9.]+$/.test(value) || value.includes(':');
  const shortName = (value: string) => (isIp(value) ? value : value.split('.')[0]);
  // \\corp.local\brest or \\DFS01\lorient: a namespace given by its path
  $: namespacePath = kind === 'dfs' ? (() => {
    const parts = host.trim().replace(/\//g, '\\').split('\\').filter(Boolean);
    return parts.length >= 2 ? `\\\\${parts[0]}\\${parts[1]}` : null;
  })() : null;
  $: duplicate = kind === 'dfs' ? null : data.endpoints.filter((endpoint) => !endpoint.isDfs).find((endpoint) => {
    const known = endpoint.host.toLowerCase();
    const names = [cleanHost, found.address, found.netbios_name, found.dns_name].filter(Boolean).map((value) => String(value).toLowerCase());
    return known && names.some((value) => value === known || (!isIp(value) && !isIp(known) && shortName(value) === shortName(known)));
  }) ?? null;
  // Windows servers hardened to check the name they are reached by (SPN) refuse an alias: their address works
  $: aliasRefused = test === 'failed' && /ACCESS_DENIED|n’a pas les droits|refusé/i.test(testMessage) && !isIp(cleanHost) && Boolean(found.address) &&
    cleanHost.toLowerCase() !== String(found.dns_name ?? '').toLowerCase();
  $: key = JSON.stringify([cleanHost, port, effectiveAccount, reuseFrom, password, secretRef]);
  $: if (testedKey && key !== testedKey) {
    testedKey = '';
    test = 'idle';
    shares = [];
    probeResult = null;
    namespaces = [];
    picked = new Set();
  }
  $: if (password && secretRef) secretRef = null;
  $: canCreate = kind === 'dfs'
    ? hostValid && Boolean(zoneId) && test === 'ok' && picked.size > 0 && !creating
    : hostValid && !duplicate && Boolean(zoneId) && Boolean(name.trim()) && test === 'ok' && !creating;

  function switchKind(next: 'filer' | 'dfs') {
    if (next === kind) return;
    kind = next;
    test = 'idle';
    testMessage = '';
    testedKey = '';
    shares = [];
    namespaces = [];
    picked = new Set();
  }

  function togglePick(name: string) {
    if (picked.has(name)) picked.delete(name);
    else picked.add(name);
    picked = picked;
  }

  function resetAnalysis() {
    analysedHost = '';
    analysis = 'idle';
    analysisMessage = '';
    found = {};
  }

  async function analyse() {
    if (!hostValid || analysis === 'running') return;
    const target = cleanHost;
    analysis = 'running';
    analysisMessage = '';
    try {
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: { kind: 'storage-endpoint', protocol: 'smb-discovery', scope: 'read', target: { host: target, port }, options: { timeout_sec: 10 }, context: { ui_origin: 'admin' } },
        intervalMs: 800,
        maxAttempts: 30
      });
      if (cleanHost !== target) return; // answer of a previous address
      analysedHost = target;
      if (!result.ok) {
        analysis = 'failed';
        analysisMessage = t(String(result.errorMessage ?? result.result?.message ?? 'Unable to analyse the server.'));
        return;
      }
      found = result.result?.details ?? {};
      analysis = found.dialect ? 'ok' : 'warn';
      if (!name.trim() || name === autoName) name = autoName = found.netbios_name || target;
      // The directory of the same domain is proposed for the groups of this server
      const source = data.sources.find((row) => row.domain && row.domain === found.domain);
      if (source && !sourceId) sourceId = source.id;
    } catch (error) {
      if (cleanHost === target) {
        analysis = 'failed';
        analysisMessage = error instanceof Error ? error.message : t('Unable to analyse the server.');
      }
    }
  }

  const secretName = () => `storage-endpoint/smb/${cleanHost || name.trim() || 'endpoint'}`;

  async function useAddress() {
    analysedHost = String(found.address);
    host = String(found.address);
    await tick(); // the test reads the new address
    await testAccount();
  }

  async function testAccount() {
    if (!hostValid || !effectiveAccount || (!reused && !password && !secretRef) || test === 'running') return;
    testedKey = '';
    test = 'running';
    testMessage = '';
    try {
      let ref = reused ? reused.secretRef : secretRef;
      if (!reused && password) {
        const resolved = await resolveCredentials(fetch, { username: effectiveAccount, password, secret_ref: null }, { secretName: secretName(), mode: 'create' });
        ref = secretRef = resolved.secret_ref ?? null;
        password = '';
      }
      const domain = effectiveAccount.includes('\\') ? effectiveAccount.split('\\')[0] : effectiveAccount.includes('@') ? effectiveAccount.split('@')[1] : null;
      if (kind === 'dfs') {
        const dnsDomain = found.domain || data.sources.find((source) => source.id === sourceId)?.domain || null;
        const read: any = await runProbeWithPolling({
          fetchFn: fetch,
          request: {
            kind: 'storage-endpoint',
            protocol: 'dfs',
            scope: 'read',
            target: { host: cleanHost, port, domain: dnsDomain, ...(namespacePath ? { path: namespacePath } : {}) },
            auth: { mode: 'ntlm', username: effectiveAccount, secret_ref: ref },
            options: { timeout_sec: 120 },
            context: { ui_origin: 'admin' }
          } as any,
          intervalMs: 1500,
          maxAttempts: 100
        });
        if (!read.ok) {
          test = 'failed';
          testMessage = humanizeFileServerMessage(t(String(read.errorMessage ?? read.result?.message ?? 'The DFS server could not be read')));
        } else {
          test = 'ok';
          dfsServer = String(read.result?.details?.server ?? cleanHost);
          namespaces = (read.result?.details?.namespaces ?? []) as Namespace[];
          picked = new Set(namespaces.map((namespace) => namespace.name));
        }
        testedKey = JSON.stringify([cleanHost, port, effectiveAccount, reuseFrom, password, secretRef]);
        return;
      }
      const final: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: buildStorageEndpointConnectProbeRequest({ host: cleanHost, port, username: effectiveAccount, domain, secretRef: ref, discover: true, timeoutSec: 30, uiOrigin: 'admin' }),
        intervalMs: 1200,
        maxAttempts: 40
      });
      if (!final.ok) {
        test = 'failed';
        testMessage = humanizeFileServerMessage(t(String(final.errorMessage ?? final.result?.message ?? 'Connection test failed')));
      } else {
        test = 'ok';
        probeResult = final.result;
        shares = parseStorageEndpointProbeRoots(final.result).map((path) => path.split(/[\\/]/).filter(Boolean).pop() ?? path);
      }
    } catch (error) {
      test = 'failed';
      testMessage = error instanceof Error ? humanizeFileServerMessage(error.message) : t('Connection test failed');
    }
    testedKey = JSON.stringify([cleanHost, port, effectiveAccount, reuseFrom, password, secretRef]);
  }

  async function createNamespaces() {
    const createdIds: number[] = [];
    const refused: string[] = [];
    for (const namespace of namespaces.filter((entry) => picked.has(entry.name))) {
      try {
        const created = await createStorageEndpoint(fetch, {
          name: namespace.name,
          description: null,
          endpoint_type: 'dfs',
          protocol: 'smb',
          identity_source_id: sourceId,
          host: dfsServer,
          port,
          auth_type: 'ntlm',
          bind_dn: effectiveAccount,
          bind_password_ref: reused ? reused.secretRef : secretRef,
          zone_id: Number(zoneId),
          is_active: true,
          status: 'active',
          capabilities: { dfs_snapshot: { ...namespace, read_at: new Date().toISOString() } }
        } as any);
        createdIds.push(created.id);
      } catch (error) {
        refused.push(`${namespace.name} : ${toUiAppError(error, t('Creation failed'), 'ui').message}`);
      }
    }
    if (refused.length) createError = refused.join(' · ');
    if (createdIds.length) {
      done = true;
      await goto(`/admin/storage-endpoints/${createdIds[0]}`);
    }
  }

  async function create() {
    if (!canCreate) return;
    creating = true;
    createError = '';
    if (kind === 'dfs') {
      try {
        await createNamespaces();
      } finally {
        creating = false;
      }
      return;
    }
    try {
      const created = await createStorageEndpoint(fetch, {
        name: name.trim(),
        description: null,
        endpoint_type: 'smb',
        protocol: 'smb',
        identity_source_id: sourceId,
        host: cleanHost,
        port,
        auth_type: 'ntlm',
        bind_dn: effectiveAccount,
        bind_password_ref: reused ? reused.secretRef : secretRef,
        zone_id: Number(zoneId),
        is_active: true,
        status: 'active',
        last_probe_status: 'success',
        last_probe_at: new Date().toISOString(),
        last_probe_message: null
      } as any);
      // The shares read by the test become the list of folders to add, without searching again
      if (probeResult) await syncStorageRootDiscoveryForEndpoint(fetch, created.id, probeResult).catch(() => null);
      done = true;
      await goto(shares.length ? `/storage-roots/add?endpoint=${created.id}` : `/admin/storage-endpoints/${created.id}`);
    } catch (error) {
      const appError = toUiAppError(error, t('Creation failed'), 'ui', { action: 'storage_endpoint_new.create' });
      createError = appError.message;
      notifyError(appError);
    } finally {
      creating = false;
    }
  }

  let done = false;
  beforeNavigate((navigation) => {
    if (navigation.type === 'leave' || done || creating) return;
    if ((host.trim() || account.trim() || password) && !window.confirm(t('Leave this page? What you entered will be lost.'))) navigation.cancel();
  });

  $: checks = [
    {
      state: analysis,
      title: t('Server'),
      detail:
        analysis === 'running' ? t('Analysis in progress…')
        : analysis === 'failed' ? analysisMessage
        : analysis === 'idle' ? t('Waiting for the address')
        : [found.dialect, found.address].filter(Boolean).join(' · ') || t('Reachable on port {port}', { port })
    },
    ...(duplicate ? [{ state: 'failed' as State, title: t('Already declared'), detail: t('This file server is already declared as {name}', { name: duplicate.name }) }] : []),
    { state: zoneId ? ('ok' as State) : ('idle' as State), title: t('Zone'), detail: zoneId ? data.zones.find((zone) => zone.id === zoneId)?.name ?? '' : t('To choose') },
    {
      state: test,
      title: t('Service account'),
      detail:
        test === 'running' ? t('Testing…')
        : test === 'ok' && kind === 'dfs' ? t('{count} namespace(s) read', { count: namespaces.length })
        : test === 'ok' ? t('{count} share(s) read', { count: shares.length })
        : test === 'failed' ? testMessage
        : t('Not tested yet')
    }
  ];
  $: pendingReason =
    !hostValid ? t('Enter the address of the server.')
    : duplicate ? t('This file server is already declared as {name}', { name: duplicate.name })
    : !zoneId ? t('Choose the zone of this server.')
    : kind === 'filer' && !name.trim() ? t('Enter a name for this server.')
    : test !== 'ok' ? t('Test the service account to continue.')
    : kind === 'dfs' && !picked.size ? t('Check at least one namespace.')
    : '';
</script>

<svelte:head><title>{t('Add a file server')} · BornToShare</title></svelte:head>

<section class="b2s-page new-server">
  <header class="head">
    <a class="crumb" href="/admin/storage-endpoints"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Servers')}</a>
    <h1>{t('Add')}</h1>
    <div class="kind" role="tablist" aria-label={t('What to add')}>
      <button type="button" role="tab" aria-selected={kind === 'filer'} class:on={kind === 'filer'} on:click={() => switchKind('filer')}><i class="bi bi-hdd-network" aria-hidden="true"></i>{t('File server')}</button>
      <button type="button" role="tab" aria-selected={kind === 'dfs'} class:on={kind === 'dfs'} on:click={() => switchKind('dfs')}><i class="bi bi-diagram-3" aria-hidden="true"></i>{t('DFS namespace')}</button>
    </div>
    <p>{kind === 'dfs' ? t('Give the DFS server or the path of a namespace: BornToShare reads its DFS folders and their targets.') : t('Give its address: BornToShare checks that it answers in SMB and reads its shares.')}</p>
  </header>

  <div class="layout">
    <fieldset class="form" disabled={creating}>
      <section class="card">
        <div class="card-head"><h2>{kind === 'dfs' ? t('DFS server or namespace') : t('Server')}</h2>{#if analysis === 'ok'}<span class="tag tag--ok">{t('Detected')}</span>{/if}</div>
        <div class="row">
          <input class="b2s-input mono big" aria-label={t('Hostname / IP')} placeholder={kind === 'dfs' ? 'dfs01.example.com  ·  \\\\example.com\\brest' : 'filer01.example.com'} bind:value={host}
            on:keydown={(event) => event.key === 'Enter' && analyse()} on:blur={() => hostValid && cleanHost !== analysedHost && analyse()} />
          <input class="b2s-input mono port" type="number" min="1" max="65535" aria-label={t('Port')} bind:value={port} />
          <button type="button" class="b2s-btn b2s-btn-secondary" disabled={!hostValid || analysis === 'running'} on:click={analyse}>
            {analysis === 'running' ? t('Analysing…') : t('Analyse')}
          </button>
        </div>
        {#if host.trim() && !hostValid}<small class="field-error">{t('Invalid hostname / IP')}</small>{/if}
        {#if analysis === 'failed'}<InlineAlert tone="error">{analysisMessage}</InlineAlert>{/if}
        {#if duplicate}<InlineAlert tone="error">{t('This file server is already declared as {name}', { name: duplicate.name })} · <a href={`/admin/storage-endpoints/${duplicate.id}`}>{t('Open it')}</a></InlineAlert>{/if}
        {#if analysis === 'ok' || analysis === 'warn'}
          <div class="found">
            <div><span>{t('Name')}</span><strong>{found.netbios_name ?? '—'}</strong></div>
            <div><span>{t('Protocol')}</span><strong>{found.dialect ?? t('Not announced')}</strong></div>
            <div><span>{t('Domain')}</span><strong>{found.domain ?? '—'}</strong></div>
          </div>
        {/if}
        <div class="grid">
          <div class="field">
            <label for="srv-zone">{t('Zone')}</label>
            <select id="srv-zone" class="b2s-input" bind:value={zoneId}>
              <option value={null}>{t('Choose a zone')}</option>
              {#each data.zones as zone (zone.id)}<option value={zone.id}>{zone.name}</option>{/each}
            </select>
            {#if !data.zones.length}<small class="field-error">{t('Create a zone before adding a storage endpoint.')}</small>{/if}
          </div>
          {#if kind === 'filer'}
            <div class="field">
              <label for="srv-name">{t('Display name')}</label>
              <input id="srv-name" class="b2s-input" bind:value={name} />
            </div>
          {/if}
          <div class="field full">
            <label for="srv-source">{t('Directory of its groups')}</label>
            <select id="srv-source" class="b2s-input" bind:value={sourceId}>
              <option value={null}>{t('None for now')}</option>
              {#each data.sources as source (source.id)}<option value={source.id}>{source.name}{source.domain ? ` (${source.domain})` : ''}</option>{/each}
            </select>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <h2>{t('Service account')}</h2>
          {#if test === 'ok'}<span class="tag tag--ok">{t('Connection successful')}</span>{/if}
          {#if test === 'failed'}<span class="tag tag--bad">{t('Connection refused')}</span>{/if}
        </div>
        {#if zoneServers.length}
          <div class="field">
            <label for="srv-reuse">{t('Account')}</label>
            <select id="srv-reuse" class="b2s-input" bind:value={reuseFrom}>
              <option value={null}>{t('Another account')}</option>
              {#each zoneServers as endpoint (endpoint.id)}<option value={endpoint.id}>{t('Same as {name} ({account})', { name: endpoint.name, account: endpoint.account })}</option>{/each}
            </select>
          </div>
        {/if}
        {#if !reused}
          <div class="grid">
            <div class="field"><label for="srv-account">{zoneServers.length ? t('Other account') : t('Account')}</label><input id="srv-account" class="b2s-input mono" autocomplete="off" placeholder="DOMAIN\svc-files" bind:value={account} /></div>
            <div class="field"><label for="srv-password">{t('Password')}</label><input id="srv-password" class="b2s-input" type="password" autocomplete="new-password" placeholder={secretRef ? t('Password stored. Type to replace it.') : ''} bind:value={password} /></div>
          </div>
        {/if}
        <button type="button" class="b2s-btn b2s-btn-secondary start" disabled={test === 'running' || !hostValid || !effectiveAccount} on:click={testAccount}>
          {test === 'running' ? t('Testing…') : kind === 'dfs' ? t('Test the account and read the namespaces') : t('Test the account and read the shares')}
        </button>
        {#if test === 'failed'}<InlineAlert tone="error">{testMessage}</InlineAlert>{/if}
        {#if aliasRefused}
          <InlineAlert tone="info">
            {t('This server may refuse the name {host}: it only accepts its own name ({name}) or its address.', { host: cleanHost, name: found.dns_name ?? found.netbios_name ?? '—' })}
            <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={useAddress}>{t('Use {address}', { address: String(found.address) })}</button>
          </InlineAlert>
        {/if}
        {#if test === 'ok' && kind === 'dfs'}
          {#if namespaces.length}
            <ul class="ns">
              {#each namespaces as namespace (namespace.name)}
                <li>
                  <label>
                    <input type="checkbox" checked={picked.has(namespace.name)} on:change={() => togglePick(namespace.name)} />
                    <span class="ns-name"><strong>{namespace.name}</strong><small class="mono">{namespace.path}</small></span>
                    <span class="tag" class:tag--ok={namespace.type === 'domain'}>{namespace.type === 'domain' ? t('Domain') : t('Standalone')}</span>
                    <small class="muted">{namespace.error ? t('Not read: {message}', { message: namespace.error }) : t('{count} DFS folder(s)', { count: namespace.links.length })}</small>
                  </label>
                </li>
              {/each}
            </ul>
            <small class="muted">{t('You manage their DFS folders right after, from the namespace page.')}</small>
          {:else}
            <small class="muted">{t('This server holds no DFS namespace.')}</small>
          {/if}
        {:else if test === 'ok'}
          {#if shares.length}
            <div class="shares">{#each shares.slice(0, 40) as share}<span>{share}</span>{/each}{#if shares.length > 40}<span>+{shares.length - 40}</span>{/if}</div>
            <small class="muted">{t('You choose those to manage right after the creation.')}</small>
          {:else}
            <small class="muted">{t('No share found: you can create one from the server page.')}</small>
          {/if}
        {/if}
      </section>
    </fieldset>

    <aside class="panel">
      <h2>{t('Configuration status')}</h2>
      <ul class="checks">
        {#each checks as check (check.title)}
          <li>
            <span class={`dot dot--${check.state}`} aria-hidden="true">{#if check.state === 'ok'}<i class="bi bi-check-lg"></i>{:else if check.state === 'failed'}<i class="bi bi-x-lg"></i>{:else if check.state === 'warn'}<i class="bi bi-exclamation-lg"></i>{/if}</span>
            <span><strong>{check.title}</strong><small>{check.detail}</small></span>
          </li>
        {/each}
      </ul>
      <button type="button" class="b2s-btn b2s-btn-primary wide" disabled={!canCreate} on:click={create}>{creating ? t('Creating…') : kind === 'dfs' ? t('Add {count} namespace(s)', { count: picked.size }) : t('Create the server')}</button>
      {#if pendingReason}<small class="muted">{pendingReason}</small>{:else}<small class="muted">{kind === 'dfs' ? t('Next: the namespace page, to manage its DFS folders.') : t('Next: choose the folders to manage.')}</small>{/if}
      {#if createError}<InlineAlert tone="error">{createError}</InlineAlert>{/if}
    </aside>
  </div>
</section>

<style>
  .new-server { padding: var(--b2s-page-padding); }
  .head { margin-bottom: 20px; }
  .head h1 { margin: 4px 0 2px; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  .head p { margin: 0; color: var(--b2s-color-text-muted); }
  .crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); text-decoration: none; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 20px; max-width: 1240px; align-items: start; }
  .form { display: flex; flex-direction: column; gap: 14px; min-width: 0; margin: 0; padding: 0; border: 0; }
  .card, .panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); box-shadow: var(--b2s-shadow-sm); }
  .card { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  .card-head { display: flex; align-items: center; gap: 10px; }
  h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; color: var(--b2s-color-heading); }
  .row { display: flex; gap: 8px; }
  .row .big { flex: 1; height: 44px; font-size: var(--b2s-fs-md); }
  .row .port { width: 90px; height: 44px; }
  .row .b2s-btn { height: 44px; }
  .mono { font-family: var(--b2s-font-mono); }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .full { grid-column: 1 / -1; }
  .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .field label { font-size: var(--b2s-text-sm); font-weight: 500; }
  .field-error { color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
  .found { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .found div { padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-accent-soft); min-width: 0; }
  .found span { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .found strong { font-size: var(--b2s-text-sm); overflow-wrap: anywhere; }
  .start { align-self: flex-start; }
  .kind { display: inline-flex; gap: 4px; margin: 12px 0 8px; padding: 4px; border-radius: var(--b2s-radius-lg); background: var(--b2s-color-neutral-soft); }
  .kind button { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border: 0; border-radius: var(--b2s-radius-md); background: transparent; color: var(--b2s-color-text-muted); font-weight: 500; cursor: pointer; }
  .kind button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); font-weight: 600; box-shadow: var(--b2s-shadow-sm); }
  .ns { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .ns li + li { border-top: 1px solid var(--b2s-color-border); }
  .ns label { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto 140px; gap: 10px; align-items: center; padding: 9px 12px; cursor: pointer; }
  .ns-name { display: flex; flex-direction: column; min-width: 0; }
  .ns-name strong { font-weight: 500; }
  .tag { padding: 2px 9px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); font-weight: 500; }
  .shares { display: flex; flex-wrap: wrap; gap: 6px; }
  .shares span { padding: 3px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .tag { padding: 2px 9px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-font-micro); font-weight: 500; }
  .tag--ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .tag--bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .panel { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 14px; padding: 18px; }
  .checks { display: grid; gap: 11px; margin: 0; padding: 0; list-style: none; }
  .checks li { display: grid; grid-template-columns: 18px 1fr; gap: 9px; font-size: var(--b2s-text-sm); }
  .checks strong, .checks small { display: block; }
  .checks small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); overflow-wrap: anywhere; }
  .dot { display: grid; place-items: center; width: 18px; height: 18px; margin-top: 1px; border-radius: 50%; background: var(--b2s-color-neutral-soft); font-size: 11px; }
  .dot--ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .dot--warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .dot--failed { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .dot--running { border: 2px solid var(--b2s-color-border-mid); border-top-color: var(--b2s-color-success-strong); background: none; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(1turn); } }
  @media (prefers-reduced-motion: reduce) { .dot--running { animation: none; } }
  .wide { width: 100%; justify-content: center; }
</style>
