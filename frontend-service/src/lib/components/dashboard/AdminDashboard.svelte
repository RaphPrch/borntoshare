<script lang="ts">
  import { formatBytes, initials, timeAgo } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { formatActivityItem } from '$lib/activity/format';
  import RequestsActivityChart from './RequestsActivityChart.svelte';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { onMount } from 'svelte';
  import { apiGetData, apiGetList, apiPostData } from '$lib/api/client';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';

  /**
   * Administrator dashboard (v2): a greeting with the day in one line, the figures in one bar, the health of the
   * file servers (one tile per server, by zone), what is left to handle, the requests and the latest actions.
   */
  interface Props {
    // data.stats: { storage_roots, storage_endpoints, admins, pending_requests, … }; data.activities: […]
    data: any;
  }

  let { data }: Props = $props();

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  const stats = data?.stats ?? data?.summary ?? {};
  // Sign-ins are frequent and say little about platform changes: kept out
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  const activities = (Array.isArray(data?.activities) ? data.activities : []).filter((a: any) => String(a?.action ?? '') !== 'auth.login');
  const requestsSeries = Array.isArray(stats?.requests_last_30_days) ? stats.requests_last_30_days : [];
  const num = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);

  // ---- what the dashboard reads after the page: folders, servers, 5S, secrets, late tasks ----
  type Root = Record<string, any>;
  type Endpoint = { storage_endpoint_id: number; storage_endpoint_name: string; storage_endpoint_type?: string | null; zone_name?: string | null;
    operational_state?: string | null; last_probe_status?: string | null; auth_username?: string | null; roots_count?: number | null };
  type MissingSecret = { kind: 'storage_endpoint' | 'identity_source'; id: number; name: string; purpose: string | null };
  type LateTask = { task: string; interval_minutes: number; last_run_at: string; late_minutes: number };
  let roots = $state<Root[]>([]);
  let endpoints = $state<Endpoint[]>([]);
  let fivesScore = $state<number | null>(null);
  let missingSecrets: MissingSecret[] = $state([]);
  let lateTasks: LateTask[] = $state([]);
  let loaded = $state(false);

  onMount(async () => {
    [roots, endpoints, missingSecrets, lateTasks] = await Promise.all([
      apiGetList<Root>(fetch, '/storage-roots/context').catch(() => []),
      apiGetList<Endpoint>(fetch, '/storage-endpoints/context').catch(() => []),
      apiGetList<MissingSecret>(fetch, '/infrastructure/secrets/missing').catch(() => []),
      apiGetList<LateTask>(fetch, '/infrastructure/schedules/late').catch(() => [])
    ]);
    loaded = true;
    if ($fivesEnabled) {
      const fives = await apiGetData<{ score: number | null }>(fetch, '/modules/fives/five-s').catch(() => null);
      fivesScore = fives?.score ?? null;
    }
  });

  const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);
  const measured = (row: Root) => row.content_size_bytes != null || ['done', 'running'].includes(String(row.measure_status ?? ''));
  let totalBytes = $derived(roots.reduce((sum, row) => sum + size(row), 0));
  let totalFiles = $derived(roots.reduce((sum, row) => sum + num(row.content_files), 0));
  let failedRoots = $derived(roots.filter((row) => String(row.measure_status ?? '') === 'failed'));
  let neverRoots = $derived(roots.filter((row) => !measured(row) && String(row.measure_status ?? '') !== 'failed'));
  let secretRoots = $derived(roots.filter((row) => num(row.password_files) + num(row.key_files) > 0));
  let secretFiles = $derived(secretRoots.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0));
  let quotaRoots = $derived(roots.filter((row) => num(row.quota_used_percent) > 85 || num(row.quota_pending_requests) > 0));
  let quotaWaiting = $derived(roots.reduce((sum, row) => sum + num(row.quota_pending_requests), 0));
  let noGuardian = $derived($governanceEnabled ? roots.filter((row) => num(row.guardians_count) === 0) : []);

  let name = $derived(String(($page.data as any)?.me?.display_name || ($page.data as any)?.me?.username || '').trim());
  // ---- Journal: the day told in one headline and one paragraph, from the figures below ----
  const todayText = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  const today = todayText.charAt(0).toUpperCase() + todayText.slice(1);
  const clock = (value: unknown) => {
    const date = new Date(String(value ?? ''));
    if (Number.isNaN(date.getTime())) return '—';
    return date.toDateString() === new Date().toDateString() ? date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : timeAgo(value as string);
  };
  let lede = $derived([
    t('{count} folder(s) on {servers} server(s)', { count: num(stats.storage_roots) || roots.length, servers: num(stats.storage_endpoints) || endpoints.length }),
    ...(totalBytes ? [t('{size} measured', { size: formatBytes(totalBytes) })] : []),
    ...($governanceEnabled && num(stats.pending_requests) ? [t('{count} request(s) to decide', { count: num(stats.pending_requests) })] : []),
    ...(secretFiles ? [t('{count} file(s) with passwords or keys', { count: secretFiles })] : []),
    ...(failedRoots.length ? [t('{count} measure(s) failed', { count: failedRoots.length })] : [])
  ].join(' · ') + '.');
  let question = $state('');
  let openStory = $state(0);
  // The folders behind a story, and the Pilot question that lists them all
  const storyFolders = (key: string): Root[] =>
    (key === 'failed' ? failedRoots : key === 'secrets-files' ? secretRoots : key === 'quota' ? quotaRoots : key === 'guardian' ? noGuardian : key === 'never' ? neverRoots : []).slice(0, 4);
  const PILOT_FOR: Record<string, string> = {
    'secrets-files': 'Quels dossiers contiennent des mots de passe ?',
    quota: 'Quotas au-delà de 85 %',
    guardian: 'Dossiers sans gardien',
    never: 'Dossiers jamais mesurés'
  };

  // ---- measure the folders never measured ----
  let measuring = $state(false);
  async function measureNever() {
    const ids = neverRoots.map((row) => Number(row.storage_root_id)).filter((id) => id > 0);
    if (!ids.length) return;
    measuring = true;
    try {
      const result = await apiPostData<{ queued: number[] }>(fetch, '/storage-roots/measure', { root_ids: ids });
      toast.success(t('Measure started on {count} folder(s).', { count: result?.queued?.length ?? ids.length }));
    } catch (error) {
      reportUiError(error, t('Unable to start the measure.'), 'dashboard.measure');
    } finally {
      measuring = false;
    }
  }

  // ---- health of the servers: one tile per server, by zone ----
  type Tile = { endpoint: Endpoint; tone: 'ok' | 'warn' | 'bad' | 'noacc' | 'dfs'; label: string };
  function tileOf(endpoint: Endpoint): Tile {
    const own = roots.filter((row) => Number(row.storage_endpoint_id) === endpoint.storage_endpoint_id);
    const state = String(endpoint.operational_state ?? '');
    const kind = String(endpoint.storage_endpoint_type ?? '').toLowerCase();
    let tone: Tile['tone'] = 'ok';
    if (kind === 'dfs') tone = 'dfs';
    else if (state === 'unreachable' || own.some((row) => String(row.measure_status ?? '') === 'failed')) tone = 'bad';
    else if (!endpoint.auth_username) tone = 'noacc';
    else if (own.some((row) => num(row.open_alerts_count) > 0)) tone = 'warn';
    const stateLabel = { ok: t('Healthy'), warn: t('Folders to review'), bad: t('Unreachable or failed'), noacc: t('No account'), dfs: t('DFS server') }[tone];
    return { endpoint, tone, label: `${endpoint.storage_endpoint_name} · ${stateLabel}${kind === 'dfs' ? '' : ` · ${t('{count} folder(s)', { count: own.length })}`}` };
  }
  let heat = $derived.by(() => {
    const zones = new Map<string, Tile[]>();
    for (const endpoint of endpoints) {
      const zone = String(endpoint.zone_name ?? '—');
      if (!zones.has(zone)) zones.set(zone, []);
      zones.get(zone)!.push(tileOf(endpoint));
    }
    return [...zones.entries()].sort((a, b) => a[0].localeCompare(b[0], 'fr'))
      .map(([zone, tiles]) => ({ zone, tiles: tiles.sort((a, b) => a.endpoint.storage_endpoint_name.localeCompare(b.endpoint.storage_endpoint_name)) }));
  });
  const openTile = (tile: Tile) =>
    tile.tone === 'dfs'
      ? goto(`/admin/storage-endpoints/${tile.endpoint.storage_endpoint_id}`)
      : goto(`/storage-roots?q=${encodeURIComponent(`serveur:${tile.endpoint.storage_endpoint_name}`)}`);

  // Right click on a tile: its actions
  let menu = $state<{ tile: Tile; at: { x: number; y: number } } | null>(null);
  let menuItems = $derived<ContextMenuItem[]>(menu?.tile.tone === 'dfs'
    ? [{ key: 'open', label: t('Open the server'), icon: 'bi-hdd-stack' }]
    : [
        { key: 'roots', label: t('See its folders'), icon: 'bi-folder2-open' },
        { key: 'measure', label: t('Measure its folders'), icon: 'bi-rulers' },
        { key: 'open', label: t('Open the server'), icon: 'bi-hdd-stack', separated: true }
      ]);
  async function onPick(key: string) {
    const tile = menu?.tile;
    if (!tile) return;
    if (key === 'open') void goto(`/admin/storage-endpoints/${tile.endpoint.storage_endpoint_id}`);
    if (key === 'roots') void openTile(tile);
    if (key === 'measure') {
      const ids = roots.filter((row) => Number(row.storage_endpoint_id) === tile.endpoint.storage_endpoint_id).map((row) => Number(row.storage_root_id));
      if (!ids.length) return;
      try {
        await apiPostData(fetch, '/storage-roots/measure', { root_ids: ids });
        toast.success(t('Measure started on {count} folder(s).', { count: ids.length }));
      } catch (error) {
        reportUiError(error, t('Unable to start the measure.'), 'dashboard.measure');
      }
    }
  }

  // ---- what is left to handle ----
  const PURPOSES: Record<string, () => string> = {
    provisioning: () => t('Manage AD groups'),
    snapshot: () => t('Snapshot inventory'),
    auth: () => t('Authenticate users')
  };
  const TASKS: Record<string, () => string> = {
    health_check: () => t('Health check'),
    data_sync: () => t('Data sync'),
    access_expiry: () => t('Access expiry'),
    dfs_read: () => t('DFS namespaces'),
    policies: () => t('Smart policies')
  };
  type Todo = { key: string; tone: 'bad' | 'warn' | 'mut'; title: string; detail: string; action: string; href?: string; run?: () => void };
  let todo = $derived.by(() => {
    const list: Todo[] = [];
    if (missingSecrets.length) list.push({ key: 'secrets', tone: 'bad', title: t('{count} password(s) missing from the secret store', { count: missingSecrets.length }),
      detail: missingSecrets.slice(0, 3).map((item) => `${item.name}${item.purpose ? ` · ${PURPOSES[item.purpose]?.() ?? item.purpose}` : ''}`).join(', '),
      action: t('Enter again'), href: missingSecrets[0]?.kind === 'storage_endpoint' ? `/admin/storage-endpoints/${missingSecrets[0].id}` : '/admin/identity-sources' });
    if (lateTasks.length) list.push({ key: 'late', tone: 'warn', title: t('{count} scheduled task(s) late', { count: lateTasks.length }),
      detail: lateTasks.map((item) => `${TASKS[item.task]?.() ?? item.task} · ${timeAgo(item.last_run_at)}`).join(', '), action: t('See'), href: '/admin/advanced-settings/infrastructure' });
    if ($governanceEnabled && num(stats.pending_requests)) list.push({ key: 'requests', tone: 'warn', title: t('{count} request(s) to decide', { count: num(stats.pending_requests) }),
      detail: num(stats.stale_pending_requests_count) ? t('{count} waiting for more than 3 days', { count: num(stats.stale_pending_requests_count) }) : t('at the guardians'), action: t('Decide'), href: '/access-requests' });
    if (num(stats.open_alerts_count)) list.push({ key: 'alerts', tone: num(stats.critical_alerts_count) ? 'bad' : 'warn', title: t('{count} open alert(s)', { count: num(stats.open_alerts_count) }),
      detail: t('{count} critical or high', { count: num(stats.critical_alerts_count) }), action: t('See'), href: '/observability?tab=alerts&severity=critical_high' });
    if (num(stats.failed_jobs_24h_count)) list.push({ key: 'jobs', tone: 'warn', title: t('{count} failed job(s) in 24 h', { count: num(stats.failed_jobs_24h_count) }),
      detail: t('Directory and file server actions'), action: t('See'), href: '/observability?tab=jobs&status=FAILED' });
    if (failedRoots.length) list.push({ key: 'failed', tone: 'bad', title: t('{count} measure(s) failed', { count: failedRoots.length }),
      detail: failedRoots.slice(0, 3).map((row) => String(row.storage_root_name ?? '')).join(', '), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:mesure-echec')}` });
    if (secretFiles) list.push({ key: 'secrets-files', tone: 'bad', title: t('{count} file(s) with passwords or keys', { count: secretFiles }),
      detail: t('in {count} folder(s)', { count: secretRoots.length }), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:mot-de-passe')}` });
    if (quotaRoots.length) list.push({ key: 'quota', tone: 'warn', title: t('{count} quota(s) over 85 %', { count: quotaRoots.length }),
      detail: quotaWaiting ? t('{count} space request(s) waiting', { count: quotaWaiting }) : t('Almost full'), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:quota-plein')}` });
    if (noGuardian.length) list.push({ key: 'guardian', tone: 'warn', title: t('{count} folder(s) without guardian', { count: noGuardian.length }),
      detail: t('Their requests go to the administrators'), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:sans-gardien')}` });
    if (neverRoots.length) list.push({ key: 'never', tone: 'mut', title: t('{count} folder(s) never measured', { count: neverRoots.length }),
      detail: t('No detailed volume, no 5S'), action: t('Measure'), run: measureNever });
    return list;
  });
  let urgent = $derived(todo.filter((item) => item.tone === 'bad').length);
  let headline = $derived(!loaded ? t('Reading the file shares…')
    : todo.length === 0 ? t('Everything is up to date.')
    : urgent ? t('{count} subject(s) to handle, {urgent} of them urgent.', { count: todo.length, urgent })
    : t('A calm day: {count} decision(s) to take.', { count: todo.length }));
</script>

<section class="v2 dash">
  <!-- Journal: the day in one headline, the score, then the stories to handle and the thread of the day -->
  <div class="jr-hero">
    <div>
      <span class="jr-kick">{today}{name ? ` · ${name}` : ''}</span>
      <h1>{headline}</h1>
      <p>{lede}</p>
      <div class="jr-acts">
        <a class="b2s-btn b2s-btn-secondary" href="/storage-roots">Storage Roots</a>
        {#if neverRoots.length}
          <button type="button" class="b2s-btn b2s-btn-primary" disabled={measuring} onclick={measureNever}>
            <i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure the {count} folder(s) never measured', { count: neverRoots.length })}
          </button>
        {/if}
      </div>
    </div>
    {#if $fivesEnabled}
      <a class="jr-score" href="/five-s"><span>{t('5S score of the file shares')}</span><b>{fivesScore ?? '—'}<i aria-hidden="true"></i></b><span>{t('on the measured folders')}</span></a>
    {:else}
      <a class="jr-score" href="/storage-roots"><span>Storage Roots</span><b>{num(stats.storage_roots) || roots.length}<i aria-hidden="true"></i></b><span>{t('on {count} server(s)', { count: num(stats.storage_endpoints) || endpoints.length })}</span></a>
    {/if}
  </div>

  <form class="jr-pilot" onsubmit={(event) => { event.preventDefault(); if (question.trim()) void goto(`/pilot?q=${encodeURIComponent(question.trim())}`); }}>
    <span class="jr-pilot__tag">Pilot</span>
    <input type="text" bind:value={question} placeholder={t('A question? « Export all the users of the folder Finance »')} aria-label={t('Ask Pilot')} />
    <button type="submit" class="b2s-btn b2s-btn-primary" disabled={!question.trim()}>{t('Ask')}</button>
  </form>

  <div class="v2-stats">
    <a class="v2-stat" href="/storage-roots"><small>Storage Roots</small><b>{num(stats.storage_roots) || roots.length}</b><span>{t('on {count} server(s)', { count: num(stats.storage_endpoints) || endpoints.length })}</span></a>
    <a class="v2-stat" href="/storage-roots"><small>{t('Measured volume')}</small><b>{loaded ? formatBytes(totalBytes) : '…'}</b><span>{t('{count} folder(s) measured', { count: roots.length - neverRoots.length - failedRoots.length })}</span></a>
    <a class="v2-stat" href={$fivesEnabled ? '/five-s/explore' : '/storage-roots'}><small>{t('Files inventoried')}</small><b>{loaded ? totalFiles.toLocaleString('fr-FR') : '…'}</b><span>{t('last measures')}</span></a>
    {#if $fivesEnabled}
      <a class="v2-stat" href="/five-s"><small>{t('Average 5S score')}</small><b>{fivesScore ?? '—'}</b><span>{t('on the measured folders')}</span></a>
    {/if}
    {#if $governanceEnabled}
      <a class="v2-stat" href="/access-requests"><small>{t('Requests to decide')}</small><b>{num(stats.pending_requests)}</b><span>{t('at the guardians')}</span></a>
    {/if}
  </div>

  <div class="jr-cols">
    <div>
      <h2 class="jr-h2">{t('Front page')}</h2>
      {#each todo as item, index (item.key)}
        {@const isOpen = openStory === index}
        <article class="jr-story">
          <button type="button" class="jr-sh" aria-expanded={isOpen} onclick={() => (openStory = isOpen ? -1 : index)}>
            <span class="jr-idx">{String(index + 1).padStart(2, '0')}</span>
            <span><h3>{item.title}</h3>{#if item.detail}<p>{item.detail}</p>{/if}<span class={`v2-tag is-${item.tone === 'mut' ? 'mut' : item.tone}`}>{item.tone === 'bad' ? t('Urgent') : item.tone === 'warn' ? t('To decide') : t('When you can')}</span></span>
            <span class="jr-plus" class:open={isOpen} aria-hidden="true">+</span>
          </button>
          {#if isOpen}
            <div class="jr-body">
              {#if storyFolders(item.key).length}
                <ul class="jr-list">{#each storyFolders(item.key) as folder (folder.storage_root_id)}<li><a href={`/storage-roots?selected=${folder.storage_root_id}`}>{folder.storage_root_name}</a><span>{folder.storage_endpoint_name ?? ''}</span></li>{/each}</ul>
              {/if}
              <div class="jr-acts">
                {#if item.href}<a class="b2s-btn b2s-btn-primary b2s-btn-sm" href={item.href}>{item.action}</a>
                {:else}<button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={measuring} onclick={item.run}>{item.action}</button>{/if}
                {#if PILOT_FOR[item.key]}<a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/pilot?q=${encodeURIComponent(PILOT_FOR[item.key])}`}><i class="bi bi-chat-square-text" aria-hidden="true"></i>{t('List and export with Pilot')}</a>{/if}
              </div>
            </div>
          {/if}
        </article>
      {:else}
        <p class="jr-calm">{loaded ? t('Nothing to handle: everything is up to date.') : t('Loading…')}</p>
      {/each}
    </div>
    <aside>
      <h2 class="jr-h2">{t('Thread of the day')} <a class="b2s-link-btn" href="/observability?tab=audit">{t('See all')}</a></h2>
      <ol class="jr-time">
        {#each activities.slice(0, 7) as a, index (index)}
          {@const rendered = formatActivityItem(a)}
          {@const who = String(a.actor_display_name ?? a.actor_display ?? (a.actor_type === 'system' ? t('System') : a.actor_id ?? '—'))}
          <li class="jr-ev" class:hot={/refus|fail|échec|alert|denied/i.test(String(a.action ?? '') + String(rendered.title ?? ''))}>
            <small>{clock(a.created_at)}</small>
            <span><b>{rendered.title ?? t('Event')}</b> · {who}{rendered.subtitle1 ? ` · ${rendered.subtitle1}` : ''}</span>
          </li>
        {:else}
          <li class="jr-ev"><span>{t('No recent activity.')}</span></li>
        {/each}
      </ol>
    </aside>
  </div>

  <div class="v2-cols">
    <div class="v2-sec">
      <div class="v2-sh"><h2>{t('Health of the file servers')}</h2><div class="v2-sh__r"><span class="v2-hint">{t('One tile per server · click: its folders · right click: actions')}</span></div></div>
      {#if heat.length}
        <div class="heat">
          {#each heat as row (row.zone)}
            <div class="heat__r">
              <span class="heat__z">{row.zone}</span>
              <div class="heat__tiles">
                {#each row.tiles as tile (tile.endpoint.storage_endpoint_id)}
                  <button type="button" class={`heat__t is-${tile.tone}`} title={tile.label} aria-label={tile.label} onclick={() => openTile(tile)}
                    oncontextmenu={(event) => { event.preventDefault(); menu = { tile, at: menuPositionFor(event) }; }}></button>
                {/each}
              </div>
            </div>
          {/each}
        </div>
        <div class="heat__legend">
          <span><i class="is-ok"></i>{t('Healthy')}</span><span><i class="is-warn"></i>{t('Folders to review')}</span><span><i class="is-bad"></i>{t('Unreachable or failed')}</span>
          <span><i class="is-noacc"></i>{t('No account')}</span><span><i class="is-dfs"></i>{t('DFS server')}</span>
        </div>
      {:else if loaded}
        <p class="v2-empty">{t('No file server yet.')} <a href="/admin/storage-endpoints/new">{t('Add a server')}</a></p>
      {/if}
    </div>

    {#if $governanceEnabled}<div class="v2-sec"><RequestsActivityChart series={requestsSeries} /></div>{/if}
  </div>
</section>

<ContextMenu open={menu != null} title={menu?.tile.endpoint.storage_endpoint_name ?? ''} subtitle={menu?.tile.endpoint.zone_name ?? ''} items={menuItems} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  .jr-hero { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 44px; align-items: end; }
  @media (max-width: 1000px) { .jr-hero { grid-template-columns: minmax(0, 1fr); } }
  .jr-kick { color: #596273; font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
  .jr-hero h1 { margin: 12px 0 0; font-size: 58px; font-weight: 700; letter-spacing: -0.045em; line-height: 1; }
  .jr-hero p { margin: 16px 0 0; max-width: 680px; color: #3f4755; font-size: 17px; line-height: 1.55; }
  .jr-acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .jr-body .jr-acts { margin-top: 0; }
  .jr-score { display: flex; flex-direction: column; gap: 8px; padding-left: 26px; border-left: 1px solid var(--b2s-color-border-soft); color: inherit; text-decoration: none; }
  .jr-score span { color: var(--b2s-color-text-muted); }
  .jr-score b { font-size: 108px; font-weight: 700; letter-spacing: -0.06em; line-height: 0.85; }
  .jr-score b i { display: inline-block; width: 18px; height: 18px; margin-left: 8px; border-radius: 50%; background: #0e1218; vertical-align: top; }
  .jr-score:hover b { color: #3f4755; }
  .jr-pilot { display: flex; align-items: center; gap: 10px; min-height: 56px; padding: 6px 6px 6px 8px; border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: var(--b2s-color-surface-soft); }
  .jr-pilot:focus-within { background: #fff; border-color: #0e1218; box-shadow: 0 0 0 3px rgba(14, 18, 24, 0.1); }
  .jr-pilot__tag { padding: 6px 12px; border-radius: 10px; background: #0e1218; color: #fff; font-weight: 700; font-size: 13px; }
  .jr-pilot input { flex: 1; border: 0; outline: 0; background: transparent; font: inherit; font-size: 16px; }
  .jr-cols { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 44px; }
  @media (max-width: 1000px) { .jr-cols { grid-template-columns: minmax(0, 1fr); } }
  .jr-h2 { display: flex; align-items: baseline; gap: 12px; margin: 0 0 6px; font-size: 26px; font-weight: 700; letter-spacing: -0.025em; }
  .jr-h2 :global(.b2s-link-btn) { margin-left: auto; font-size: 13px; letter-spacing: 0; }
  .jr-story { border-top: 1px solid var(--b2s-color-border-soft); }
  .jr-sh { width: 100%; display: grid; grid-template-columns: 56px minmax(0, 1fr) 28px; gap: 16px; align-items: start; padding: 20px 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .jr-sh:focus-visible { outline: 2px solid #0e1218; outline-offset: 2px; }
  .jr-idx { color: #cdd2db; font-size: 28px; font-weight: 800; line-height: 1; }
  .jr-sh h3 { margin: 0; font-size: 19px; font-weight: 600; letter-spacing: -0.015em; }
  .jr-sh p { margin: 6px 0 10px; color: #4a5262; line-height: 1.5; }
  .jr-plus { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--b2s-color-border); border-radius: 50%; transition: transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .jr-plus.open { transform: rotate(45deg); border-color: #0e1218; background: #0e1218; color: #fff; }
  .jr-body { display: flex; flex-direction: column; gap: 12px; padding: 0 0 22px 72px; }
  .jr-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
  .jr-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px dashed var(--b2s-color-border-soft); }
  .jr-list a { color: inherit; font-weight: 600; text-decoration: none; }
  .jr-list a:hover { color: #3f4755; text-decoration: underline; }
  .jr-list span { color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: 12px; }
  .jr-calm { color: var(--b2s-color-text-muted); }
  .jr-time { position: relative; display: flex; flex-direction: column; margin: 8px 0 0; padding: 0 0 0 22px; list-style: none; }
  .jr-time::before { content: ''; position: absolute; left: 5px; top: 6px; bottom: 6px; width: 1px; background: var(--b2s-color-border-soft); }
  .jr-ev { position: relative; padding: 0 0 16px; line-height: 1.45; }
  .jr-ev::before { content: ''; position: absolute; left: -21px; top: 6px; width: 9px; height: 9px; border: 2px solid #0e1218; border-radius: 50%; background: #fff; }
  .jr-ev.hot::before { border-color: #0e1218; background: #0e1218; }
  .jr-ev small { display: block; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 700; }
  .jr-ev b { font-weight: 600; }
  .v2-cols.is-single { grid-template-columns: minmax(0, 1fr); }
  .heat { display: flex; flex-direction: column; gap: 7px; }
  .heat__r { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; align-items: center; }
  .heat__z { overflow: hidden; color: #3f4755; font-size: 12.5px; text-overflow: ellipsis; white-space: nowrap; }
  .heat__tiles { display: flex; flex-wrap: wrap; gap: 5px; }
  .heat__t { width: 34px; height: 28px; padding: 0; border: 0; border-radius: 7px; cursor: pointer; transition: transform var(--b2s-motion-fast) var(--b2s-ease-out), box-shadow var(--b2s-motion-fast); }
  .heat__t:hover { transform: translateY(-2px); box-shadow: 0 6px 12px -6px rgba(14, 18, 24, 0.5); }
  .heat__t:focus-visible { outline: 3px solid #0e1218; outline-offset: 2px; }
  .is-ok { background: #0b7a4b; } .is-warn { background: #b86200; } .is-bad { background: #c23a3a; } .is-noacc { background: #fdefd9; box-shadow: inset 0 0 0 1px #e8c28f; } .is-dfs { background: #3f4755; }
  .heat__legend { display: flex; flex-wrap: wrap; gap: 14px; color: var(--b2s-color-text-muted); font-size: 12px; }
  .heat__legend i { display: inline-block; width: 10px; height: 10px; margin-right: 5px; border-radius: 3px; vertical-align: -1px; }
  .dash__av { width: 30px; height: 30px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #eef0f4;
    color: #0e1218; font-size: 11px; font-weight: 700; }
</style>
