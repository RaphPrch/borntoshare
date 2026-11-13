<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import ExtensionIcon from '$lib/components/settings/ExtensionIcon.svelte';
  import { formatDateTime, timeAgo } from '$lib/utils/format';
  import {
    listExtensionDeliveries,
    listExtensions,
    renewCentreonToken,
    saveExtension,
    testExtension,
    type Extension,
    type ExtensionDelivery,
    type ExtensionKey,
    type ExtensionRoutes
  } from '$lib/api/extensions';

  /**
   * Advanced Settings › Extensions: where the events of BornToShare go (syslog, Splunk) and the Centreon check.
   * OpenTelemetry, Grafana and ServiceNow are announced, not configurable yet.
   */
  type Product = { key: string; name: string; category: () => string; description: () => string; live: boolean };
  const PRODUCTS: Product[] = [
    { key: 'syslog', name: 'Syslog', category: () => t('Logs and SIEM'), description: () => t('Audit and alerts to a syslog collector (RFC 5424, CEF or JSON).'), live: true },
    { key: 'splunk', name: 'Splunk', category: () => t('Logs and SIEM'), description: () => t('Audit and alerts to the HTTP Event Collector of Splunk.'), live: true },
    { key: 'otel', name: 'OpenTelemetry', category: () => t('Observability'), description: () => t('Traces, metrics and logs of the services in OTLP, to your collector.'), live: true },
    { key: 'grafana', name: 'Grafana', category: () => t('Observability'), description: () => t('Logs to Loki, annotations on your dashboards, metrics to scrape.'), live: true },
    { key: 'centreon', name: 'Centreon', category: () => t('Supervision and ITSM'), description: () => t('Centreon checks the state of the BornToShare components.'), live: true },
    { key: 'servicenow', name: 'ServiceNow ITSM', category: () => t('Supervision and ITSM'), description: () => t('One incident per critical alert, resolved when the alert closes.'), live: true }
  ];
  const SEVERITIES: Array<{ key: ExtensionRoutes['min_severity']; label: () => string }> = [
    { key: 'info', label: () => t('Information') },
    { key: 'warning', label: () => t('Warning') },
    { key: 'high', label: () => t('High') },
    { key: 'critical', label: () => t('Critical') }
  ];

  let extensions: Extension[] = $state([]);
  let deliveries: ExtensionDelivery[] = $state([]);
  let healthPath = $state('/monitoring/health');
  let loading = $state(true);

  const TAB_KEYS = ['catalog', 'routing', 'deliveries'];
  let active = $derived(TAB_KEYS.includes($page.url.searchParams.get('tab') ?? '') ? String($page.url.searchParams.get('tab')) : 'catalog');
  let failedCount = $derived(extensions.filter((item) => item.enabled && item.stats?.last_status === 'failed').length);
  let tabs = $derived([
    { key: 'catalog', label: t('Extensions'), icon: 'bi-plug', count: extensions.filter((item) => item.enabled).length },
    { key: 'routing', label: t('What goes where'), icon: 'bi-signpost-split' },
    { key: 'deliveries', label: t('Deliveries'), icon: 'bi-send-check', count: failedCount || null }
  ]);
  function setTab(key: string) {
    const url = new URL($page.url);
    url.searchParams.set('tab', key);
    goto(url, { replaceState: true, noScroll: true, keepFocus: true });
  }

  async function load() {
    try {
      const data = await listExtensions(fetch);
      extensions = data.extensions;
      healthPath = data.health_path;
      deliveries = await listExtensionDeliveries(fetch);
    } catch (error) {
      reportUiError(error, t('Unable to load the extensions.'), 'extensions.load');
    } finally {
      loading = false;
    }
  }
  onMount(load);

  const byKey = (key: string) => extensions.find((item) => item.key === key) ?? null;
  const stateOf = (item: Extension | null): { variant: 'success' | 'error' | 'muted' | 'warning'; label: string } =>
    !item?.configured ? { variant: 'muted', label: t('Not configured') }
      : !item.enabled ? { variant: 'warning', label: t('Disabled') }
      : item.stats?.last_status === 'failed' ? { variant: 'error', label: t('Failing') }
      : { variant: 'success', label: t('Active') };
  const flows = (item: Extension | null) =>
    !item ? '' : item.key === 'centreon' ? t('Platform state, on request') : item.key === 'servicenow' ? t('Incidents from the alerts') : [item.routes.audit ? t('Audit') : '', item.routes.alerts ? t('Alerts') : ''].filter(Boolean).join(' · ') || '—';

  // ---- drawer -----------------------------------------------------------------------------------
  let editing: Extension | null = $state(null);
  let form: Record<string, any> = $state({});
  let routes: ExtensionRoutes = $state({ audit: true, alerts: true, min_severity: 'high' });
  let enabled = $state(false);
  let secret = $state('');
  let saving = $state(false);
  let testing = $state(false);
  let testResult: { ok: boolean; text: string } | null = $state(null);
  let shownToken = $state('');

  function open(key: string) {
    const item = byKey(key);
    if (!item) return;
    editing = item;
    form = { transport: 'udp', format: 'rfc5424', facility: 'local4', app_name: 'borntoshare', verify: 'public', port: 514, ...item.config };
    routes = { ...item.routes };
    enabled = item.configured ? item.enabled : true;
    secret = '';
    lokiSecret = '';
    grafanaSecret = '';
    if (key === 'otel') form = { logs: true, traces: true, metrics: true, sample_ratio: 0.1, service_namespace: 'borntoshare', environment: 'production', ...item.config };
    if (key === 'servicenow') {
      form = { auth: 'basic', category: 'software', ...item.config };
      if (!item.configured) routes = { ...routes, audit: false, min_severity: 'critical' };
    }
    if (key === 'grafana') form = { labels: 'app=borntoshare', ...item.config };
    testResult = null;
    shownToken = '';
  }
  // Grafana keeps its Loki and annotation tokens together; an empty field keeps the saved value
  let lokiSecret = $state('');
  let grafanaSecret = $state('');
  const payload = () => {
    if (editing?.key === 'grafana') {
      const keys = Object.fromEntries(Object.entries({ loki: lokiSecret.trim(), grafana: grafanaSecret.trim() }).filter(([, value]) => value));
      return { enabled, config: form, routes, secret: Object.keys(keys).length ? JSON.stringify(keys) : null };
    }
    return { enabled, config: form, routes, secret: secret.trim() || null };
  };

  async function runTest() {
    if (!editing) return;
    testing = true;
    try {
      const result = await testExtension(fetch, editing.key, payload());
      testResult = result.ok
        ? { ok: true, text: t('Test event delivered in {ms} ms.', { ms: result.latency_ms ?? 0 }) }
        : { ok: false, text: t('The test failed: {error}', { error: result.error ?? '' }) };
    } catch (error) {
      reportUiError(error, t('The test could not run.'), 'extensions.test');
    } finally {
      testing = false;
    }
  }
  async function save() {
    if (!editing) return;
    saving = true;
    try {
      const result = await saveExtension(fetch, editing.key, payload());
      toast.success(t('Extension saved.'));
      await load();
      if (result.token) {
        shownToken = result.token;
        editing = byKey(editing.key);
      } else editing = null;
    } catch (error) {
      reportUiError(error, t('Unable to save the extension.'), 'extensions.save');
    } finally {
      saving = false;
    }
  }
  async function toggle(key: string) {
    const item = byKey(key);
    if (!item) return;
    if (!item.configured) return open(key);
    try {
      await saveExtension(fetch, item.key, { enabled: !item.enabled, config: item.config, routes: item.routes });
      await load();
    } catch (error) {
      reportUiError(error, t('Unable to save the extension.'), 'extensions.toggle');
    }
  }
  async function renewToken() {
    try {
      shownToken = (await renewCentreonToken(fetch)).token;
      toast.success(t('New token: the previous one no longer works.'));
    } catch (error) {
      reportUiError(error, t('Unable to renew the token.'), 'extensions.token');
    }
  }
  let checkUrl = $derived(`${$page.url.origin}${healthPath}`);
  let syslogPreview =
    $derived(form.format === 'json'
      ? `{"app":"${form.app_name || 'borntoshare'}","type":"audit","action":"access_request.created","actor":"paul.martin","target":"Paris - Finance",…}`
      : form.format === 'cef'
        ? 'CEF:0|BornToShare|BornToShare|1.0|access_request.created|access_request.created REQ-927|3|act=access_request.created suser=paul.martin fname=Paris - Finance'
        : `<${(({ local0: 16, local1: 17, local2: 18, local3: 19, local4: 20, local5: 21, local6: 22, local7: 23, auth: 4 } as Record<string, number>)[form.facility] ?? 20) * 8 + 6}>1 2026-11-04T10:41:55Z b2s-core ${form.app_name || 'borntoshare'} - access_request.created [b2s@32473 actor="paul.martin" target="Paris - Finance"] access_request.created REQ-927`);

  // ---- routing grid ---------------------------------------------------------------------------------
  let routingBusy = $state(false);
  async function saveRoutes() {
    routingBusy = true;
    try {
      for (const item of extensions.filter((entry) => entry.events.length && entry.configured)) {
        await saveExtension(fetch, item.key, { enabled: item.enabled, config: item.config, routes: item.routes });
      }
      toast.success(t('Routing saved.'));
      await load();
    } catch (error) {
      reportUiError(error, t('Unable to save the routing.'), 'extensions.routes');
    } finally {
      routingBusy = false;
    }
  }
  const nameOf = (key: string) => PRODUCTS.find((product) => product.key === key)?.name ?? key;
</script>

<div class="ext">
  <Tabs {tabs} activeKey={active} onChange={setTab} ariaLabel={t('Extensions')} />
  <p class="ext__hint"><i class="bi bi-info-circle" aria-hidden="true"></i>{t('Events leave from core-service in the background and are tried 3 times; tokens are kept in the vault of BornToShare.')}</p>

  {#if loading}
    <div class="ext__panel"><LoadingState skeleton="rows" rows={4}>{t('Loading…')}</LoadingState></div>
  {:else if active === 'catalog'}
    <div class="ext__cards">
      {#each PRODUCTS as product, index (product.key)}
        {@const item = byKey(product.key)}
        {@const state = stateOf(item)}
        {#if index === 0 || PRODUCTS[index - 1].category() !== product.category()}<h3 class="ext__cat">{product.category()}</h3>{/if}
        <article class="ext__card" class:is-soon={!product.live}>
          <header>
            <ExtensionIcon product={product.key} />
            <div><h4>{product.name}</h4><p>{product.description()}</p></div>
          </header>
          {#if product.live}
            <div class="ext__line"><StatusBadge compact showDot variant={state.variant} label={state.label} /><small>{flows(item)}</small></div>
            {#if item?.stats}
              <div class="ext__spark" aria-label={t('Sends of the last 24 hours')}>
                {#each item.stats.buckets as count, bucket}<i class:bad={item.stats.failed_buckets[bucket] > 0} style="height:{Math.max(8, Math.min(100, (count + item.stats.failed_buckets[bucket]) * 12))}%"></i>{/each}
              </div>
              <small class="ext__muted">{t('{sent} sent, {failed} failed in 24 h · {ago}', { sent: item.stats.sent, failed: item.stats.failed, ago: timeAgo(item.stats.last_at) })}</small>
            {:else}
              <small class="ext__muted">{product.key === 'centreon' ? t('Nothing is sent: Centreon asks.') : t('Nothing sent yet.')}</small>
            {/if}
            <footer>
              <button type="button" class="b2s-link-btn" onclick={() => open(product.key)}>{item?.configured ? t('Configure') : t('Connect')} ›</button>
              <label class="form-check form-switch" title={item?.enabled ? t('Disable') : t('Enable')}>
                <input class="form-check-input" type="checkbox" role="switch" checked={Boolean(item?.enabled)} onchange={() => toggle(product.key)} aria-label={t('Enable {name}', { name: product.name })} />
              </label>
            </footer>
          {:else}
            <div class="ext__line"><StatusBadge compact variant="muted" label={t('Coming soon')} /></div>
          {/if}
        </article>
      {/each}
    </div>
  {:else if active === 'routing'}
    <section class="ext__panel ext__routing">
      <table>
        <thead><tr><th>{t('Event')}</th>{#each extensions.filter((item) => item.events.length) as item (item.key)}<th>{nameOf(item.key)}</th>{/each}</tr></thead>
        <tbody>
          <tr>
            <td><b>{t('Audit log')}</b><small>{t('Sign-ins, requests, decisions, changes of rights')}</small></td>
            {#each extensions.filter((item) => item.events.length) as item (item.key)}<td><input type="checkbox" bind:checked={item.routes.audit} disabled={!item.configured || !item.events.includes('audit')} aria-label={t('Audit to {name}', { name: nameOf(item.key) })} /></td>{/each}
          </tr>
          <tr>
            <td><b>{t('Governance alerts')}</b><small>{t('New alerts: ACL gaps, folders open to everyone, missing guardians')}</small></td>
            {#each extensions.filter((item) => item.events.length) as item (item.key)}<td><input type="checkbox" bind:checked={item.routes.alerts} disabled={!item.configured || !item.events.includes('alerts')} aria-label={t('Alerts to {name}', { name: nameOf(item.key) })} /></td>{/each}
          </tr>
          <tr>
            <td><b>{t('Alerts from')}</b><small>{t('Minimal severity of the alerts sent')}</small></td>
            {#each extensions.filter((item) => item.events.length) as item (item.key)}
              <td><select class="b2s-input ext__sev" bind:value={item.routes.min_severity} disabled={!item.configured || !item.routes.alerts}>{#each SEVERITIES as severity (severity.key)}<option value={severity.key}>{severity.label()}</option>{/each}</select></td>
            {/each}
          </tr>
        </tbody>
      </table>
      <footer><small class="ext__muted">{t('Centreon receives nothing: it asks for the platform state. An extension not configured yet is greyed.')}</small><button type="button" class="b2s-btn b2s-btn-primary" disabled={routingBusy} onclick={saveRoutes}><i class="bi bi-check2" aria-hidden="true"></i>{t('Save')}</button></footer>
    </section>
  {:else}
    <section class="ext__panel">
      {#if deliveries.length}
        <table class="ext__log">
          <thead><tr><th>{t('Time')}</th><th>{t('Extension')}</th><th>{t('Event')}</th><th>{t('Result')}</th></tr></thead>
          <tbody>
            {#each deliveries as row (row.id)}
              <tr>
                <td class="ext__mono" title={formatDateTime(row.created_at)}>{timeAgo(row.created_at)}</td>
                <td>{nameOf(row.ext_key)}</td>
                <td>{row.summary}</td>
                <td>
                  {#if row.status === 'delivered'}<StatusBadge compact variant="success" label={t('Delivered · {ms} ms', { ms: row.latency_ms ?? 0 })} />
                  {:else}<StatusBadge compact variant="error" label={t('Failed after {count} attempt(s)', { count: row.attempts })} /><small class="ext__err">{row.detail}</small>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <EmptyStateInline message={t('No delivery in the last 7 days.')} />
      {/if}
    </section>
  {/if}
</div>

<Drawer open={Boolean(editing)} onClose={() => (editing = null)} title={editing ? nameOf(editing.key) : ''} subtitle={editing ? PRODUCTS.find((p) => p.key === editing?.key)?.description() ?? '' : ''} size="lg">
  {#snippet headerIcon()}
    {#if editing}<ExtensionIcon product={editing.key} size={36} />{/if}
  {/snippet}
  {#if editing}
    <div class="ext__form">
      {#if editing.key === 'syslog'}
        <h3>{t('Destination')}</h3>
        <div class="ext__grid">
          <label>{t('Server')}<input class="b2s-input" bind:value={form.host} placeholder="siem.corp.local" /></label>
          <label>{t('Port')}<input class="b2s-input" type="number" min="1" max="65535" bind:value={form.port} /></label>
        </div>
        <div class="ext__field"><span>{t('Transport')}</span><SegmentedFilter bind:value={form.transport} options={[{ key: 'udp', label: 'UDP' }, { key: 'tcp', label: 'TCP' }, { key: 'tls', label: 'TLS' }]} /></div>
        {#if form.transport === 'tls'}
          <label class="ext__field">{t('Certificate of the collector')}
            <select class="b2s-input" bind:value={form.verify}><option value="public">{t('Check (public authority)')}</option><option value="file">{t('Check (capsule-runner/certs/syslog-ca.pem)')}</option><option value="none">{t('Do not check')}</option></select>
          </label>
        {/if}
        <h3>{t('Format')}</h3>
        <div class="ext__grid">
          <label>{t('Format')}<select class="b2s-input" bind:value={form.format}><option value="rfc5424">RFC 5424</option><option value="cef">CEF (ArcSight)</option><option value="json">JSON</option></select></label>
          <label>{t('Facility')}<select class="b2s-input" bind:value={form.facility}>{#each ['local0', 'local1', 'local2', 'local3', 'local4', 'local5', 'local6', 'local7', 'auth'] as facility}<option>{facility}</option>{/each}</select></label>
          <label>{t('Application name')}<input class="b2s-input" bind:value={form.app_name} /></label>
        </div>
        <div class="ext__field"><span>{t('Preview of a line')}</span><code class="ext__preview">{syslogPreview}</code></div>
      {:else if editing.key === 'splunk'}
        <h3>{t('HTTP Event Collector')}</h3>
        <label class="ext__field">{t('HEC URL')}<input class="b2s-input" bind:value={form.url} placeholder="https://splunk.corp.local:8088/services/collector" /></label>
        <div class="ext__grid">
          <label>{t('HEC token')}<input class="b2s-input" type="password" bind:value={secret} placeholder={editing.has_secret ? t('Unchanged') : ''} autocomplete="new-password" /><small>{t('Kept in the vault of BornToShare')}</small></label>
          <label>{t('Index')}<input class="b2s-input" bind:value={form.index} placeholder="borntoshare" /></label>
          <label>{t('Sourcetype')}<input class="b2s-input" bind:value={form.sourcetype} placeholder="borntoshare:audit" /></label>
          <label>{t('Certificate')}<select class="b2s-input" bind:value={form.verify}><option value="public">{t('Check (public authority)')}</option><option value="file">{t('Check (capsule-runner/certs/splunk-ca.pem)')}</option><option value="none">{t('Do not check')}</option></select></label>
        </div>
        {#if editing.stats?.last_status === 'failed'}<p class="ext__result is-bad">{t('Last send refused: {error}', { error: editing.stats.last_detail ?? '' })}</p>{/if}
      {:else if editing.key === 'grafana'}
        <h3>{t('Logs to Loki')}</h3>
        <label class="ext__field">{t('Loki push URL')}<input class="b2s-input" bind:value={form.loki_url} placeholder="https://loki.corp.local/loki/api/v1/push" /></label>
        <div class="ext__grid">
          <label>{t('Account (optional)')}<input class="b2s-input" bind:value={form.loki_user} autocomplete="off" /></label>
          <label>{t('Password or token')}<input class="b2s-input" type="password" bind:value={lokiSecret} placeholder={editing.has_secret ? t('Unchanged') : ''} autocomplete="new-password" /></label>
          <label>{t('Labels')}<input class="b2s-input" bind:value={form.labels} placeholder="app=borntoshare,env=prod" /></label>
        </div>
        <h3>{t('Annotations')}</h3>
        <div class="ext__grid">
          <label>{t('Grafana URL')}<input class="b2s-input" bind:value={form.grafana_url} placeholder="https://grafana.corp.local" /></label>
          <label>{t('Service account token')}<input class="b2s-input" type="password" bind:value={grafanaSecret} placeholder={editing.has_secret ? t('Unchanged') : ''} autocomplete="new-password" /><small>{t('Right « annotations:write »')}</small></label>
          <label>{t('Dashboard (UID, optional)')}<input class="b2s-input" bind:value={form.dashboard_uid} /></label>
        </div>
        <h3>{t('Metrics')}</h3>
        <div class="ext__field"><span>{t('Prometheus scrape (job)')}</span><code class="ext__preview">{`- job_name: borntoshare\n  scheme: ${$page.url.protocol.replace(':', '')}\n  metrics_path: /monitoring/metrics\n  authorization:\n    credentials: <token>\n  static_configs:\n    - targets: ['${$page.url.host}']`}</code></div>
        {#if shownToken}<div class="ext__field"><span>{t('Metrics token (shown once)')}</span><code class="ext__preview is-token">{shownToken}</code></div>
        {:else}<small class="ext__muted">{editing.has_secret ? t('A metrics token is set (created when the extension was enabled).') : t('The metrics token is created when you save with the extension enabled.')}</small>{/if}
      {:else if editing.key === 'otel'}
        <h3>{t('OTLP collector')}</h3>
        <label class="ext__field">{t('Endpoint (OTLP/HTTP)')}<input class="b2s-input" bind:value={form.endpoint} placeholder="https://otel-collector.corp.local:4318" /></label>
        <label class="ext__field">{t('Headers')}<input class="b2s-input" type="password" bind:value={secret} placeholder={editing.has_secret ? t('Unchanged') : 'Authorization=Bearer …'} autocomplete="new-password" /><small>{t('key=value separated by ; · kept in the vault')}</small></label>
        <div class="ext__grid">
          <label>service.namespace<input class="b2s-input" bind:value={form.service_namespace} /></label>
          <label>deployment.environment<input class="b2s-input" bind:value={form.environment} /></label>
        </div>
        <h3>{t('Signals')}</h3>
        <div class="ext__checks">
          <label><input type="checkbox" bind:checked={form.logs} /> {t('Logs: the events chosen in « What goes where »')}</label>
          <label><input type="checkbox" bind:checked={form.traces} /> {t('Traces: the requests of core-service')}</label>
          <label><input type="checkbox" bind:checked={form.metrics} /> {t('Metrics: the figures of the platform, every minute')}</label>
          <label class="ext__ratio">{t('Sampling of the traces')}<input class="b2s-input" type="number" min="0" max="1" step="0.05" bind:value={form.sample_ratio} /></label>
        </div>
      {:else if editing.key === 'servicenow'}
        <h3>{t('Instance')}</h3>
        <label class="ext__field">{t('Instance URL')}<input class="b2s-input" bind:value={form.instance_url} placeholder="https://corp.service-now.com" /></label>
        <div class="ext__field"><span>{t('Authentication')}</span><SegmentedFilter bind:value={form.auth} options={[{ key: 'basic', label: t('Service account') }, { key: 'oauth', label: 'OAuth (client credentials)' }]} /></div>
        <div class="ext__grid">
          {#if form.auth === 'oauth'}<label>Client ID<input class="b2s-input" bind:value={form.client_id} /></label>
          {:else}<label>{t('Account')}<input class="b2s-input" bind:value={form.username} autocomplete="off" /></label>{/if}
          <label>{form.auth === 'oauth' ? 'Client secret' : t('Password')}<input class="b2s-input" type="password" bind:value={secret} placeholder={editing.has_secret ? t('Unchanged') : ''} autocomplete="new-password" /><small>{t('Kept in the vault of BornToShare')}</small></label>
        </div>
        <h3>{t('Incidents')}</h3>
        <div class="ext__grid">
          <label>{t('Assignment group')}<input class="b2s-input" bind:value={form.assignment_group} placeholder="IAM - File access" /></label>
          <label>{t('Configuration item (CI)')}<input class="b2s-input" bind:value={form.cmdb_ci} placeholder="BornToShare" /></label>
          <label>{t('Create from')}<select class="b2s-input" bind:value={routes.min_severity}>{#each SEVERITIES as severity (severity.key)}<option value={severity.key}>{severity.label()}</option>{/each}</select></label>
        </div>
        <p class="ext__result is-info">{t('One incident per alert (correlation id = key of the alert): no duplicate when the alert comes back. Critical → impact/urgency 1, High → 2. When the alert closes in BornToShare, the incident is resolved with a note.')}</p>
      {:else}
        <p class="ext__result is-info">{t('Centreon calls the check below with its token: 200 « OK » or « WARNING », 503 « CRITICAL » with the components down.')}</p>
        <div class="ext__field"><span>{t('Check URL')}</span><code class="ext__preview">{checkUrl}</code></div>
        <div class="ext__field"><span>{t('Command for Centreon')}</span><code class="ext__preview">check_http -H {$page.url.hostname} {$page.url.protocol === 'https:' ? '-S ' : ''}-u {healthPath} -k 'X-Monitoring-Token: $_SERVICEB2STOKEN$' -e 200</code></div>
        {#if shownToken}
          <div class="ext__field"><span>{t('Token (shown once: copy it into Centreon)')}</span><code class="ext__preview is-token">{shownToken}</code></div>
        {:else if editing.has_secret}
          <div class="ext__line"><small class="ext__muted">{t('A token is set. Renewing it stops the previous one.')}</small><button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={renewToken}><i class="bi bi-arrow-repeat" aria-hidden="true"></i>{t('Renew the token')}</button></div>
        {:else}
          <small class="ext__muted">{t('The token is created when you save with the extension enabled.')}</small>
        {/if}
      {/if}
      {#if testResult}<p class="ext__result" class:is-ok={testResult.ok} class:is-bad={!testResult.ok}>{testResult.text}</p>{/if}
    </div>
  {/if}
  {#snippet footerStart()}
  
      <label class="form-check form-switch ext__enable"><input class="form-check-input" type="checkbox" role="switch" bind:checked={enabled} />{enabled ? t('Enabled') : t('Disabled')}</label>
    
  {/snippet}
  {#snippet footer()}
  
      <button type="button" class="b2s-btn b2s-btn-secondary" disabled={saving} onclick={() => (editing = null)}>{t('Cancel')}</button>
      {#if editing?.events.length}<button type="button" class="b2s-btn b2s-btn-secondary" disabled={testing || saving} onclick={runTest}><i class="bi bi-lightning-charge" aria-hidden="true"></i>{testing ? t('Testing…') : t('Send a test')}</button>{/if}
      <button type="button" class="b2s-btn b2s-btn-primary" disabled={saving} onclick={save}><i class="bi {saving ? 'bi-arrow-repeat' : 'bi-check2'}" aria-hidden="true"></i>{t('Save')}</button>
    
  {/snippet}
</Drawer>

<style>
  .ext { display: flex; flex-direction: column; gap: 14px; }
  .ext__hint { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ext__panel { padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ext__cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  .ext__field > :global(.seg) { align-self: flex-start; }
  .ext__cat { grid-column: 1 / -1; margin: 6px 0 -4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .ext__card { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .ext__card.is-soon { opacity: 0.7; }
  .ext__card header { display: flex; gap: 12px; align-items: flex-start; }
  .ext__card h4 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ext__card p { margin: 2px 0 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ext__line { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .ext__line small, .ext__muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ext__spark { display: flex; align-items: flex-end; gap: 2px; height: 26px; }
  .ext__spark i { flex: 1; border-radius: 2px; background: var(--b2s-color-border); }
  .ext__spark i.bad { background: var(--b2s-color-danger-strong); }
  .ext__card footer { display: flex; align-items: center; justify-content: space-between; margin-top: auto; padding-top: 10px; border-top: 1px solid var(--b2s-color-border); }
  .ext__card footer .form-check { margin: 0; }
  .ext__routing table, .ext__log { width: 100%; border-collapse: collapse; }
  .ext__routing th, .ext__routing td, .ext__log th, .ext__log td { padding: 10px 12px; border-bottom: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); text-align: left; }
  .ext__routing td:not(:first-child), .ext__routing th:not(:first-child) { text-align: center; }
  .ext__routing th, .ext__log th { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; background: var(--b2s-color-surface-soft, #f6f7f9); }
  .ext__routing td small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ext__routing input[type='checkbox'] { width: 16px; height: 16px; }
  .ext__sev { width: auto; height: 32px; margin: 0 auto; }
  .ext__routing footer { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding-top: 12px; }
  .ext__mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .ext__err { display: block; margin-top: 2px; color: var(--b2s-color-danger-strong); font-size: var(--b2s-fs-xs); }
  .ext__form { display: flex; flex-direction: column; gap: 14px; }
  .ext__form h3 { margin: 4px 0 -4px; font-size: var(--b2s-fs-md); font-weight: 600; }
  .ext__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 14px; }
  .ext__grid label, .ext__field { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .ext__grid small { color: var(--b2s-color-text-muted); font-weight: 400; font-size: var(--b2s-fs-xs); }
  .ext__field > span { font-weight: 600; }
  .ext__preview { display: block; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft, #f6f7f9); font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); font-weight: 400; white-space: pre-wrap; word-break: break-all; color: var(--b2s-color-text-muted); }
  .ext__preview.is-token { color: var(--b2s-color-text); font-size: var(--b2s-fs-sm); user-select: all; }
  .ext__result { margin: 0; padding: 10px 12px; border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); }
  .ext__result.is-ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .ext__result.is-bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .ext__result.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .ext__checks { display: flex; flex-direction: column; gap: 8px; font-size: var(--b2s-fs-sm); }
  .ext__checks label { display: flex; align-items: center; gap: 8px; }
  .ext__ratio input { width: 90px; }
  .ext__enable { display: flex; align-items: center; gap: 8px; margin: 0; }
</style>
