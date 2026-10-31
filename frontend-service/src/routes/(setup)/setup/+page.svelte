<script lang="ts">
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { createZone, updateZone, putZoneProvisioningPolicy } from '$lib/api/zones';
  import { createIdentitySource, updateIdentitySource, runIdentitySnapshot } from '$lib/api/identity-sources';
  import { createStorageEndpoint, updateStorageEndpoint } from '$lib/api/storage-endpoints';
  import { createIdentity } from '$lib/api/identity';
  import { searchIdentityDirectory } from '$lib/api/identity-browser';
  import { resolveCredentials } from '$lib/api/credentials';
  import { completeSetup } from '$lib/api/admin-advanced-settings';
  import { runProbeWithPolling, buildIdentitySourceProbeRequest } from '$lib/jobs/probe-runner';
  import { buildStorageEndpointConnectProbeRequest } from '$lib/jobs/probe-builders';
  import { extractDomainFromUsername } from '$lib/jobs/storage-endpoint-probe';

  export let data: { status: Record<string, any> };

  type StepKey = 'zone' | 'directory' | 'server' | 'identities' | 'roles' | 'done';
  type Group = { key: string; title: string; item: Record<string, any>; role: 'platform_admin' | 'user' };
  type Check = { label: string; ok: boolean | null; value: string };

  const STEPS: { key: StepKey; label: () => string; hint: () => string }[] = [
    { key: 'zone', label: () => t('Zone'), hint: () => t('Where your servers are') },
    { key: 'directory', label: () => t('Directory'), hint: () => t('Who your users are') },
    { key: 'server', label: () => t('File server'), hint: () => t('Where the folders are') },
    { key: 'identities', label: () => t('Identities'), hint: () => t('Who can sign in') },
    { key: 'roles', label: () => t('Roles'), hint: () => t('Who administers') },
    { key: 'done', label: () => t('Ready'), hint: () => t('Your first folders') }
  ];

  const status = data.status ?? {};
  const baseToDomain = (dn: string) =>
    dn.split(',').map((part) => part.trim()).filter((part) => /^dc=/i.test(part)).map((part) => part.slice(3)).join('.');

  let zoneId: number | null = status.zone?.id ?? null;
  let zone = { name: status.zone?.name ?? '', description: status.zone?.description ?? '' };

  let sourceId: number | null = status.directory?.id ?? null;
  let directory = {
    name: status.directory?.name ?? '',
    flavor: (status.directory?.directory_flavor ?? 'ad') as 'ad' | 'openldap',
    protocol: (status.directory?.protocol ?? 'ldaps') as 'ldap' | 'ldaps',
    host: status.directory?.host ?? '',
    port: Number(status.directory?.port ?? 636),
    base: status.directory?.base_dn ?? '',
    account: status.directory?.bind_dn ?? '',
    password: '',
    ref: (status.directory?.bind_password_ref ?? null) as string | null,
    verify: status.directory ? Boolean(status.directory.tls_verify) : true,
    ca: status.directory?.tls_ca_pem ?? '',
    tlsName: status.directory?.tls_server_name ?? '',
    ou: status.group_ou ?? ''
  };
  let directoryTested = Boolean(sourceId);
  let directoryChecks: Check[] = [];

  let serverId: number | null = status.server?.id ?? null;
  let server = {
    name: status.server?.name ?? '',
    host: status.server?.host ?? '',
    account: status.server?.bind_dn ?? '',
    password: '',
    ref: (status.server?.bind_password_ref ?? null) as string | null
  };
  let serverTested = Boolean(serverId);
  let serverChecks: Check[] = [];

  let groups: Group[] = [];
  let picked: Record<string, Group> = {};
  let query = '';
  let groupsLoading = false;
  let groupsError = '';
  let snapshotStarted = false;

  // Resume at the first step left to do
  const firstStep = !zoneId ? 0 : !sourceId ? 1 : !serverId ? 2 : status.imported_groups > 0 ? 5 : 3;
  let at = firstStep;
  let top = firstStep;
  let busy = false;
  let testing = false;
  let errorMessage = '';

  $: current = STEPS[at].key;
  $: pickedGroups = Object.values(picked);
  $: admins = pickedGroups.filter((group) => group.role === 'platform_admin').length;
  $: isLdaps = directory.protocol === 'ldaps';
  $: directoryReady =
    !!directory.name.trim() && !!directory.host.trim() && !!directory.base.trim() && !!directory.account.trim() &&
    (!!directory.password || !!directory.ref) && !!directory.ou.trim();
  $: serverReady = !!server.name.trim() && !!server.host.trim() && !!server.account.trim() && (!!server.password || !!server.ref);
  $: canContinue =
    current === 'zone' ? !!zone.name.trim()
    : current === 'directory' ? directoryReady && directoryTested
    : current === 'server' ? serverReady && serverTested
    : current === 'identities' ? pickedGroups.length > 0 || status.imported_groups > 0
    : true;
  $: placed = [
    { label: t('Zone'), value: top > 0 ? zone.name : '', step: 0 },
    { label: t('Directory'), value: top > 1 ? `${directory.name} · ${directory.protocol.toUpperCase()}` : '', step: 1 },
    { label: t('File server'), value: top > 2 ? `${server.name} · ${server.host}` : '', step: 2 },
    { label: t('Identities'), value: top > 3 ? t('{count} group(s)', { count: pickedGroups.length || status.imported_groups || 0 }) : '', step: 3 },
    { label: t('Roles'), value: top > 4 ? t('{count} administrator group(s)', { count: admins }) : '', step: 4 }
  ];

  function touchDirectory() {
    directoryTested = false;
    directoryChecks = [];
  }

  function touchServer() {
    serverTested = false;
    serverChecks = [];
  }

  function setFlavor(flavor: 'ad' | 'openldap') {
    directory.flavor = flavor;
    touchDirectory();
  }

  function setProtocol(protocol: 'ldap' | 'ldaps') {
    directory.protocol = protocol;
    if (protocol === 'ldaps' && Number(directory.port) === 389) directory.port = 636;
    if (protocol === 'ldap' && Number(directory.port) === 636) directory.port = 389;
    touchDirectory();
  }

  const message = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);

  async function storedRef(secretName: string, username: string, password: string, ref: string | null): Promise<string | null> {
    if (!password) return ref;
    const resolved = await resolveCredentials(fetch, { username, password, secret_ref: ref }, { secretName, mode: 'edit' });
    return resolved.secret_ref ?? ref;
  }

  const detailChecks = (details: Record<string, any>): Check[] =>
    [
      isLdaps ? { label: t('Server certificate'), ok: details.tls_ok ?? null, value: details.tls_ok === false ? t('Refused') : details.tls_verified ? t('Verified') : t('Not verified') } : null,
      { label: t('Service account sign-in'), ok: details.bind_ok ?? null, value: details.bind_ok ? t('Succeeded') : t('Failed') },
      { label: t('Reading the base DN'), ok: details.base_dn_ok ?? null, value: details.base_dn_ok ? t('Allowed') : t('Refused') }
    ].filter((check): check is Check => check !== null && check.ok !== null);

  async function testDirectory() {
    testing = true;
    errorMessage = '';
    directoryChecks = [];
    try {
      const protocol = directory.protocol;
      directory.ref = await storedRef(`identity-source/${directory.host.trim()}`, directory.account.trim(), directory.password, directory.ref);
      directory.password = '';
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: buildIdentitySourceProbeRequest({
          protocol,
          host: directory.host.trim(),
          port: Number(directory.port),
          baseDn: directory.base.trim(),
          bindDn: directory.account.trim(),
          secretRef: directory.ref,
          authMode: 'simple',
          tlsVerify: directory.verify,
          tlsCaPem: directory.ca,
          tlsServerName: directory.tlsName,
          identitySourceId: sourceId,
          uiOrigin: 'wizard'
        }),
        intervalMs: 1200,
        maxAttempts: 30
      });
      directoryTested = Boolean(result.ok);
      const details = result.result?.details ?? {};
      directoryChecks = detailChecks(details);
      if (!result.ok) errorMessage = t(String(result.result?.details?.hint ?? result.errorMessage ?? 'The connection test failed.'));
    } catch (error) {
      directoryTested = false;
      errorMessage = message(error, t('The connection test failed.'));
    } finally {
      testing = false;
    }
  }

  async function testServer() {
    testing = true;
    errorMessage = '';
    serverChecks = [];
    try {
      const username = server.account.trim();
      server.ref = await storedRef(`storage-endpoint/smb/${server.host.trim()}`, username, server.password, server.ref);
      server.password = '';
      const result: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: buildStorageEndpointConnectProbeRequest({
          protocol: 'smb',
          host: server.host.trim(),
          port: 445,
          username,
          domain: extractDomainFromUsername(username),
          secretRef: server.ref,
          password: null,
          discover: true,
          timeoutSec: 20,
          uiOrigin: 'wizard'
        }),
        intervalMs: 1200,
        maxAttempts: 30
      });
      serverTested = Boolean(result.ok);
      const details = result.result?.details ?? {};
      if (result.ok) {
        const shares = Array.isArray(details.roots) ? details.roots.length : null;
        serverChecks = [
          { label: t('Connection to the server'), ok: true, value: t('Succeeded') },
          ...(shares !== null ? [{ label: t('Shares found'), ok: true, value: String(shares) }] : []),
          { label: t('Reading the rights'), ok: details.acl_capability !== false, value: details.acl_capability === false ? t('Refused') : t('Allowed') }
        ];
      } else {
        errorMessage = t(String(result.result?.message ?? result.errorMessage ?? 'The connection test failed.'));
      }
    } catch (error) {
      serverTested = false;
      errorMessage = message(error, t('The connection test failed.'));
    } finally {
      testing = false;
    }
  }

  async function loadGroups() {
    if (!sourceId) return;
    groupsLoading = true;
    groupsError = '';
    try {
      const found: any = await searchIdentityDirectory(fetch, {
        sourceId,
        q: query.trim(),
        scope: 'subtree',
        principalType: 'group',
        enabledOnly: false,
        limit: 100
      });
      groups = (found.items ?? []).map((item: any) => {
        const key = String(item.dn ?? item.external_id ?? item.username);
        return { key, item, title: String(item.display_name ?? item.username ?? item.dn), role: picked[key]?.role ?? 'user' };
      });
    } catch (error) {
      groups = [];
      groupsError = message(error, t('Unable to read the groups of the directory.'));
    } finally {
      groupsLoading = false;
    }
  }

  function togglePick(group: Group, checked: boolean) {
    const next = { ...picked };
    if (checked) next[group.key] = group;
    else delete next[group.key];
    picked = next;
  }

  async function saveStep() {
    if (current === 'zone') {
      const code = zone.name.normalize('NFD').replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 16) || 'ZONE';
      const payload = { name: zone.name.trim(), code, description: zone.description.trim() || null };
      if (zoneId) await updateZone(fetch, zoneId, payload);
      else zoneId = Number((await createZone(fetch, payload) as any)?.id);
    }
    if (current === 'directory') {
      const payload: any = {
        type: 'ad',
        name: directory.name.trim(),
        directory_flavor: directory.flavor,
        protocol: directory.protocol,
        host: directory.host.trim(),
        port: Number(directory.port),
        base_dn: directory.base.trim(),
        domain_name: baseToDomain(directory.base) || null,
        bind_dn: directory.account.trim(),
        bind_password_ref: directory.ref,
        tls_verify: directory.verify,
        tls_ca_pem: directory.ca.trim() || null,
        tls_server_name: directory.tlsName.trim() || null,
        capabilities: { auth: true, import_groups: true, snapshot_enabled: true, provisioning: true },
        auth_enabled: true,
        is_active: true
      };
      if (sourceId) await updateIdentitySource(fetch, sourceId, payload);
      else sourceId = Number((await createIdentitySource(fetch, payload) as any)?.id);
      await putZoneProvisioningPolicy(fetch, Number(zoneId), {
        enabled: true,
        ou_strategy: 'zone_static',
        static_ou_dn: directory.ou.trim(),
        base_ou_dn: directory.ou.trim()
      } as any);
      if (!snapshotStarted) {
        snapshotStarted = true;
        await runIdentitySnapshot(fetch, sourceId, 'full').catch(() => null);
      }
    }
    if (current === 'server') {
      const payload: any = {
        name: server.name.trim(),
        endpoint_type: 'smb',
        protocol: 'smb',
        host: server.host.trim(),
        port: 445,
        auth_type: 'ntlm',
        bind_dn: server.account.trim(),
        bind_password_ref: server.ref,
        identity_source_id: sourceId,
        zone_id: zoneId,
        is_active: true,
        status: 'active'
      };
      if (serverId) await updateStorageEndpoint(fetch, serverId, payload);
      else serverId = Number((await createStorageEndpoint(fetch, payload))?.id);
    }
    if (current === 'roles') {
      for (const group of pickedGroups) {
        await createIdentity(fetch, {
          identity_type: 'group',
          auth_source: 'ad',
          identity_source_id: sourceId,
          application_role: group.role,
          principal: {
            type: 'group',
            external_id: group.item.external_id ?? group.item.dn ?? group.item.username,
            dn: group.item.dn ?? null,
            username: group.item.username ?? null,
            upn: null,
            display_name: group.title,
            email: null
          }
        } as any);
      }
      picked = {};
    }
  }

  async function next() {
    if (!canContinue || busy) return;
    busy = true;
    errorMessage = '';
    try {
      await saveStep();
      at += 1;
      top = Math.max(top, at);
      if (STEPS[at].key === 'identities') void loadGroups();
    } catch (error) {
      errorMessage = message(error, t('Unable to save this step.'));
    } finally {
      busy = false;
    }
  }

  function goToStep(index: number) {
    if (index > top) return;
    errorMessage = '';
    at = index;
    if (STEPS[at].key === 'identities') void loadGroups();
  }

  async function finish(path: string) {
    busy = true;
    try {
      await completeSetup(fetch);
      await goto(path, { invalidateAll: true });
    } catch (error) {
      errorMessage = message(error, t('Unable to save this step.'));
      busy = false;
    }
  }

  if (firstStep === 3) void loadGroups();
</script>

<svelte:head><title>{t('First start')} · BornToShare</title></svelte:head>

<div class="sp">
  <aside class="sp-path" aria-label={t('Setup steps')}>
    <div class="sp-brand"><b aria-hidden="true">B</b><strong>BornToShare</strong></div>
    <h1>{t('Let\'s set everything up.')} <mark>{t('Six steps.')}</mark></h1>
    <p>{t('The application is empty. Each step is saved: you can leave and come back here.')}</p>
    <ol class="sp-steps">
      {#each STEPS as step, index}
        {@const state = index === at ? 'cur' : index < top ? 'done' : ''}
        <li class={state}>
          <button type="button" class={`sp-step ${state}`} disabled={index > top} aria-current={index === at ? 'step' : undefined} on:click={() => goToStep(index)}>
            <span class="sp-pip" aria-hidden="true">{state === 'done' ? '✓' : index + 1}</span>
            <span><strong>{step.label()}</strong><small>{step.hint()}</small></span>
          </button>
        </li>
      {/each}
    </ol>
  </aside>

  <main class="sp-stage">
    <section class="sp-panel">
      <div class="sp-form">
        <div>
          <span class="sp-count">{t('Step {at} of {total}', { at: at + 1, total: STEPS.length })}</span>
          {#if current === 'zone'}
            <h2>{t('Start by creating a zone')}</h2>
            <p class="sp-lead">{t('A zone groups the servers of a place or an entity. You can add others later.')}</p>
          {:else if current === 'directory'}
            <h2>{t('Connect your directory')}</h2>
            <p class="sp-lead">{t('Your colleagues sign in with it, and BornToShare creates in it the groups that give the accesses.')}</p>
          {:else if current === 'server'}
            <h2>{t('Add a file server')}</h2>
            <p class="sp-lead">{t('The server that holds the folders to govern in the zone {zone}.', { zone: zone.name })}</p>
          {:else if current === 'identities'}
            <h2>{t('Choose who can sign in')}</h2>
            <p class="sp-lead">{t('Import the groups of the directory whose members will use BornToShare.')}</p>
          {:else if current === 'roles'}
            <h2>{t('Give each group a role')}</h2>
            <p class="sp-lead">{t('The role decides what can be done in BornToShare, not what can be opened on the file server.')}</p>
          {:else}
            <h2>{t('BornToShare is ready')}</h2>
            <p class="sp-lead">{t('What is left: say which folders to govern, and who their guardians are.')}</p>
          {/if}
        </div>

        {#if current === 'zone'}
          <div class="sp-grid">
            <label class="sp-f" for="sp-zone-name">{t('Zone name')}<input id="sp-zone-name" bind:value={zone.name} autocomplete="off" /></label>
            <label class="sp-f" for="sp-zone-desc">{t('Description')}<input id="sp-zone-desc" bind:value={zone.description} autocomplete="off" /><small>{t('Optional')}</small></label>
          </div>
        {:else if current === 'directory'}
          <div class="sp-row">
            <div class="sp-seg" role="group" aria-label={t('Directory type')}>
              <button type="button" class:on={directory.flavor === 'ad'} on:click={() => setFlavor('ad')}>Active Directory</button>
              <button type="button" class:on={directory.flavor === 'openldap'} on:click={() => setFlavor('openldap')}>OpenLDAP</button>
            </div>
            <div class="sp-seg" role="group" aria-label={t('Connection')}>
              <button type="button" class:on={isLdaps} on:click={() => setProtocol('ldaps')}>LDAPS</button>
              <button type="button" class:on={!isLdaps} on:click={() => setProtocol('ldap')}>LDAP</button>
            </div>
          </div>
          {#if !isLdaps}
            <p class="sp-note warn">{t('LDAP · port 389. The password of the service account travels unencrypted.')}</p>
          {/if}
          <div class="sp-grid" on:input={touchDirectory}>
            <label class="sp-f" for="sp-dir-name">{t('Name')}<input id="sp-dir-name" bind:value={directory.name} autocomplete="off" /></label>
            <label class="sp-f" for="sp-dir-host">{t('Hostname / IP')}<input id="sp-dir-host" class="mono" bind:value={directory.host} autocomplete="off" /></label>
            <label class="sp-f" for="sp-dir-port">{t('Port')}<input id="sp-dir-port" type="number" min="1" max="65535" bind:value={directory.port} /></label>
            <label class="sp-f" for="sp-dir-base">{t('Base DN')}<input id="sp-dir-base" class="mono" bind:value={directory.base} placeholder="DC=example,DC=test" autocomplete="off" /></label>
            <label class="sp-f" for="sp-dir-account">{t('Service account')}<input id="sp-dir-account" class="mono" bind:value={directory.account} autocomplete="off" placeholder={directory.flavor === 'ad' ? 'svc-b2s@example.test' : 'cn=b2s,ou=services,dc=example,dc=test'} /></label>
            <label class="sp-f" for="sp-dir-password">{t('Password')}<input id="sp-dir-password" type="password" bind:value={directory.password} autocomplete="new-password" placeholder={directory.ref ? t('Already saved') : ''} /><small>{t('Stored encrypted, never shown again.')}</small></label>
            <label class="sp-f wide" for="sp-dir-ou">{t('Where to create the groups of this zone')}<input id="sp-dir-ou" class="mono" bind:value={directory.ou} placeholder="OU=B2S Groups,DC=example,DC=test" autocomplete="off" /></label>
            {#if isLdaps}
              <label class="sp-switch wide" for="sp-dir-verify"><input id="sp-dir-verify" type="checkbox" bind:checked={directory.verify} on:change={touchDirectory} /> {t('Check the server certificate')}</label>
              {#if directory.verify}
                <label class="sp-f wide" for="sp-dir-ca">{t('Certificate authority (PEM)')}<textarea id="sp-dir-ca" rows="4" bind:value={directory.ca} placeholder="-----BEGIN CERTIFICATE-----"></textarea><small>{t('Public certificate of the authority that signed the domain controller. Leave empty if it is a public authority.')}</small></label>
                <label class="sp-f" for="sp-dir-tls">{t('Name in the certificate')}<input id="sp-dir-tls" class="mono" bind:value={directory.tlsName} placeholder="dc01.example.test" autocomplete="off" /><small>{t('Only if the host is an IP address.')}</small></label>
              {:else}
                <p class="sp-note warn wide">{t('The connection is encrypted, but the identity of the server is not verified.')}</p>
              {/if}
            {/if}
          </div>
          <div class="sp-test">
            <button type="button" class="sp-btn" disabled={!directoryReady || testing} on:click={testDirectory}>
              {#if testing}<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>{/if}
              {testing ? t('Testing…') : t('Test the directory')}
            </button>
            {#if directoryChecks.length}
              <div class="sp-checks">
                {#each directoryChecks as check}<div><span>{check.label}</span><i class={check.ok ? 'ok' : 'bad'}>{check.value}</i></div>{/each}
              </div>
            {/if}
          </div>
        {:else if current === 'server'}
          <div class="sp-grid" on:input={touchServer}>
            <label class="sp-f" for="sp-srv-name">{t('Name')}<input id="sp-srv-name" bind:value={server.name} autocomplete="off" /></label>
            <label class="sp-f" for="sp-srv-host">{t('Hostname / IP')}<input id="sp-srv-host" class="mono" bind:value={server.host} autocomplete="off" /></label>
            <label class="sp-f" for="sp-srv-account">{t('Service account')}<input id="sp-srv-account" class="mono" bind:value={server.account} autocomplete="off" placeholder="EXAMPLE\svc-b2s-files" /><small>{t('Full control on the shares to govern. Local administrator only to create shares from BornToShare.')}</small></label>
            <label class="sp-f" for="sp-srv-password">{t('Password')}<input id="sp-srv-password" type="password" bind:value={server.password} autocomplete="new-password" placeholder={server.ref ? t('Already saved') : ''} /><small>{t('Stored encrypted, never shown again.')}</small></label>
          </div>
          <div class="sp-test">
            <button type="button" class="sp-btn" disabled={!serverReady || testing} on:click={testServer}>
              {#if testing}<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>{/if}
              {testing ? t('Testing…') : t('Test the connection')}
            </button>
            {#if serverChecks.length}
              <div class="sp-checks">
                {#each serverChecks as check}<div><span>{check.label}</span><i class={check.ok ? 'ok' : 'bad'}>{check.value}</i></div>{/each}
              </div>
            {/if}
          </div>
        {:else if current === 'identities'}
          <form class="sp-search" on:submit|preventDefault={loadGroups}>
            <input type="search" bind:value={query} aria-label={t('Search a group of the directory')} placeholder={t('Search a group of the directory…')} />
            <button type="submit" class="sp-btn sm">{t('Search')}</button>
          </form>
          {#if groupsLoading}
            <p class="sp-note"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span> {t('Reading the directory…')}</p>
          {:else if groupsError}
            <p class="sp-note warn">{groupsError}</p>
          {:else if groups.length === 0}
            <p class="sp-note">{t('No group found. The first inventory of the directory can take a moment: search again shortly.')}</p>
          {:else}
            <div class="sp-list">
              {#each groups as group (group.key)}
                <label class="sp-pick">
                  <input type="checkbox" checked={Boolean(picked[group.key])} on:change={(event) => togglePick(group, event.currentTarget.checked)} />
                  <span><strong>{group.title}</strong><small class="mono">{group.item.dn ?? ''}</small></span>
                </label>
              {/each}
            </div>
          {/if}
          {#if pickedGroups.length}
            <p class="sp-note tip">{t('{count} group(s) selected.', { count: pickedGroups.length })}</p>
          {/if}
        {:else if current === 'roles'}
          {#if pickedGroups.length}
            <div class="sp-list">
              {#each pickedGroups as group (group.key)}
                <div class="sp-pick static">
                  <span><strong>{group.title}</strong></span>
                  <select aria-label={t('Role of {name}', { name: group.title })} bind:value={picked[group.key].role}>
                    <option value="platform_admin">{t('Administrator')}</option>
                    <option value="user">{t('User')}</option>
                  </select>
                </div>
              {/each}
            </div>
            {#if admins === 0}
              <p class="sp-note warn">{t('No administrator group: only the local account will be able to administer. Choose one so as not to depend on it.')}</p>
            {/if}
          {:else}
            <p class="sp-note">{t('The groups of this step are already imported. Their roles can be changed in Identities.')}</p>
          {/if}
          <p class="sp-note">{t('The guardian role is not given here: it is given folder by folder, with a minimum of guardians per folder.')}</p>
        {:else}
          <div class="sp-checks">
            <div><span>{t('Zone')}</span><i class="ok">{zone.name}</i></div>
            <div><span>{t('Directory')}</span><i class="ok">{directory.name}</i></div>
            <div><span>{t('File server')}</span><i class="ok">{server.name}</i></div>
          </div>
          <div class="sp-row">
            <button type="button" class="sp-btn pri" disabled={busy} on:click={() => finish('/storage-roots')}>{t('Add my first folders')}</button>
            <button type="button" class="sp-btn" disabled={busy} on:click={() => finish('/dashboard')}>{t('Go to the dashboard')}</button>
          </div>
        {/if}

        {#if errorMessage}<p class="sp-note bad" role="alert">{errorMessage}</p>{/if}
      </div>

      <div class="sp-foot">
        <span>
          {#if current === 'done'}
            {t('This setup will not be shown again. Each setting stays editable in its menu.')}
          {:else if (current === 'directory' && !directoryTested) || (current === 'server' && !serverTested)}
            {t('Test the connection to continue.')}
          {:else}
            {t('Each step is saved: you will resume here at your next sign-in.')}
          {/if}
        </span>
        {#if at > 0}<button type="button" class="sp-btn" disabled={busy} on:click={() => goToStep(at - 1)}>{t('Back')}</button>{/if}
        {#if current !== 'done'}
          <button type="button" class="sp-btn pri" disabled={!canContinue || busy} on:click={next}>{busy ? t('Saving…') : t('Continue')}</button>
        {/if}
      </div>
    </section>
  </main>

  <aside class="sp-panel sp-built" aria-label={t('What is in place')}>
    <h3>{t('What is in place')}</h3>
    {#each placed as node}
      <div class="sp-node" class:empty={!node.value} class:on={node.step === at}>
        <small>{node.label}</small>
        <strong>{node.value || t('Not yet')}</strong>
      </div>
    {/each}
  </aside>
</div>

<style>
  .sp { display: flex; gap: 18px; align-items: flex-start; min-height: 100vh; max-width: 1480px; margin: 0 auto; padding: 24px 28px 36px; }
  .sp-path { flex: 0 0 300px; display: flex; flex-direction: column; gap: 22px; }
  .sp-brand { display: flex; align-items: center; gap: 12px; }
  .sp-brand b { width: 40px; height: 40px; border-radius: 12px; background: var(--b2s-accent); color: #10140a; display: flex; align-items: center; justify-content: center; font-weight: 700; }
  .sp-brand strong { font-size: 18px; font-weight: 600; letter-spacing: -.01em; }
  .sp-path h1 { margin: 0; font-size: 38px; line-height: 1.05; font-weight: 600; letter-spacing: -.03em; }
  .sp-path h1 mark { background: var(--b2s-accent); color: inherit; padding: 0 .14em; border-radius: .14em; -webkit-box-decoration-break: clone; box-decoration-break: clone; }
  .sp-path > p { margin: 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .sp-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .sp-step { width: 100%; display: flex; align-items: flex-start; gap: 12px; padding: 10px; border: 0; border-radius: 12px; background: none; color: inherit; text-align: left; cursor: pointer; }
  .sp-step:disabled { cursor: default; }
  .sp-step:not(:disabled):hover { background: var(--b2s-color-neutral-soft); }
  .sp-step.cur { background: var(--b2s-color-surface); box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .sp-pip { flex: none; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .cur .sp-pip { background: var(--b2s-accent); color: #10140a; }
  .done .sp-pip { background: var(--b2s-color-success); color: #fff; }
  .sp-step strong { display: block; font-weight: 500; }
  .sp-step small { display: block; color: var(--b2s-color-text-muted); font-size: 12px; }
  .sp-stage { flex: 1 1 520px; min-width: 0; }
  .sp-panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: 18px; box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .sp-form { padding: 26px 28px; display: flex; flex-direction: column; gap: 20px; }
  .sp-count { font-size: 12px; color: var(--b2s-color-text-muted); }
  .sp-form h2 { margin: 3px 0 0; font-size: 30px; line-height: 1.1; font-weight: 600; letter-spacing: -.025em; }
  .sp-lead { margin: 7px 0 0; max-width: 62ch; color: var(--b2s-color-text-muted); font-size: 15px; }
  .sp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
  .sp-f { display: flex; flex-direction: column; gap: 6px; min-width: 0; margin: 0; font-weight: 500; font-size: 13px; }
  .wide { grid-column: 1 / -1; }
  .sp-f input, .sp-f textarea, .sp-pick select { width: 100%; min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); color: inherit; font-size: 14px; font-weight: 400; }
  .sp-f textarea { padding: 10px 12px; font-family: var(--b2s-font-mono, monospace); font-size: 12px; resize: vertical; }
  .sp-f input.mono { font-family: var(--b2s-font-mono, monospace); font-size: 13px; }
  .sp-f small { font-weight: 400; color: var(--b2s-color-text-muted); font-size: 12px; }
  .sp-switch { display: flex; align-items: center; gap: 10px; margin: 0; cursor: pointer; }
  .sp-switch input { width: 18px; height: 18px; accent-color: var(--b2s-color-success); }
  .sp-row { display: flex; flex-wrap: wrap; gap: 10px; }
  .sp-seg { display: inline-flex; gap: 3px; padding: 3px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .sp-seg button { min-height: 38px; padding: 0 14px; border: 0; border-radius: 9px; background: transparent; color: var(--b2s-color-text-muted); cursor: pointer; }
  .sp-seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 2px rgba(14, 18, 24, .12); }
  .sp-btn { min-height: 44px; padding: 0 16px; border-radius: 12px; border: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); color: inherit; font-weight: 500; cursor: pointer; }
  .sp-btn.sm { min-height: 36px; font-size: 13px; }
  .sp-btn:disabled { opacity: .5; cursor: default; }
  .sp-btn.pri { background: var(--b2s-accent); border-color: #9ad632; color: #10140a; font-weight: 600; }
  .sp-test { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .sp-checks { align-self: stretch; display: flex; flex-direction: column; border: 1px solid var(--b2s-color-border); border-radius: 14px; overflow: hidden; }
  .sp-checks div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; padding: 10px 14px; }
  .sp-checks div + div { border-top: 1px solid var(--b2s-color-border); }
  .sp-checks i { font-style: normal; font-size: 12px; font-weight: 500; padding: 3px 9px; border-radius: 999px; }
  .sp-checks i.ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success); }
  .sp-checks i.bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger); }
  .sp-note { margin: 0; padding: 12px 14px; border-radius: 12px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .sp-note.warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning); }
  .sp-note.bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger); }
  .sp-note.tip { background: var(--b2s-color-success-soft); color: var(--b2s-color-success); }
  .sp-search { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 4px 0 14px; border-radius: 12px; border: 1px solid var(--b2s-color-border); }
  .sp-search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: inherit; }
  .sp-list { display: flex; flex-direction: column; max-height: 420px; overflow-y: auto; border: 1px solid var(--b2s-color-border); border-radius: 14px; }
  .sp-pick { display: flex; align-items: center; gap: 12px; margin: 0; padding: 10px 14px; cursor: pointer; }
  .sp-pick.static { cursor: default; justify-content: space-between; }
  .sp-pick + .sp-pick { border-top: 1px solid var(--b2s-color-border); }
  .sp-pick input { width: 18px; height: 18px; accent-color: var(--b2s-color-success); }
  .sp-pick span { min-width: 0; }
  .sp-pick strong { display: block; font-weight: 500; }
  .sp-pick small { color: var(--b2s-color-text-muted); font-size: 12px; overflow-wrap: anywhere; }
  .sp-pick select { width: auto; min-height: 38px; }
  .sp-foot { display: flex; align-items: center; gap: 8px; padding: 14px 28px; border-top: 1px solid var(--b2s-color-border); }
  .sp-foot span { flex: 1 1 auto; font-size: 12px; color: var(--b2s-color-text-muted); }
  .sp-built { flex: 0 0 300px; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
  .sp-built h3 { margin: 0; font-size: 16px; font-weight: 600; }
  .sp-node { padding: 11px 13px; border-radius: 14px; border: 1px solid var(--b2s-color-border); }
  .sp-node small { display: block; font-size: 12px; color: var(--b2s-color-text-muted); }
  .sp-node strong { display: block; font-weight: 500; overflow-wrap: anywhere; }
  .sp-node.empty { border-style: dashed; color: var(--b2s-color-text-muted); }
  .sp-node.empty strong { font-weight: 400; color: var(--b2s-color-text-muted); }
  .sp-node.on { background: var(--b2s-accent-soft); border-color: #9ad632; }
</style>
