<script lang="ts">
  import { formatBytes, formatLongDay, initials, timeAgo } from '$lib/utils/format';
  import { t } from '$lib/i18n';
  import { page } from '$app/stores';
  import ThreadOfTheDay from './ThreadOfTheDay.svelte';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { onMount } from 'svelte';
  import { apiGetData, apiGetList, apiPostData } from '$lib/api/client';
  import { foldersMatching } from '$lib/components/storage-roots/folder-query';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';

  /**
   * Administrator dashboard (v2): a greeting with the day in one line, the figures, what is left to handle and the
   * thread of the day (the problems of the platform).
   */
  interface Props {
    // data.stats: { storage_roots, storage_endpoints, admins, pending_requests, … }; data.activities: […]
    data: any;
  }

  let { data }: Props = $props();

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  const stats = data?.stats ?? data?.summary ?? {};
  // Thread of the day of the platform: what went wrong (health checks, DFS reads, syncs, jobs, provisioning steps),
  // not the sign-ins and sign-outs nor the decisions of the guardians (a refusal is not a problem of the platform)
  const isIssue = (a: any) => {
    const action = String(a?.action ?? '');
    const outcome = String(a?.outcome ?? '').toLowerCase();
    const severity = String(a?.severity ?? '').toLowerCase();
    return !action.startsWith('auth.') && (['failure', 'error'].includes(outcome) || ['warning', 'error', 'critical'].includes(severity));
  };
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  const activities = (Array.isArray(data?.activities) ? data.activities : []).filter(isIssue);
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
  // A reading that failed: the front page does not claim that everything is up to date
  let loadFailed = $state(false);
  function soft<T>(request: Promise<T[]>): Promise<T[]> {
    return request.catch(() => {
      loadFailed = true;
      return [] as T[];
    });
  }

  async function load() {
    loaded = false;
    loadFailed = false;
    [roots, endpoints, missingSecrets, lateTasks] = await Promise.all([
      // The columns of the journal and the tiles only (the whole folder list weighed megabytes)
      soft(apiGetList<Root>(fetch, '/storage-roots/context', { fields: 'storage_root_id,storage_root_name,root_path,dfs_path,zone_name,storage_endpoint_id,storage_endpoint_name,content_size_bytes,estimated_size_bytes,content_files,measure_status,password_files,key_files,quota_used_percent,quota_warn_percent,quota_pending_requests,guardians_count,open_alerts_count' })),
      soft(apiGetList<Endpoint>(fetch, '/storage-endpoints/context')),
      soft(apiGetList<MissingSecret>(fetch, '/infrastructure/secrets/missing')),
      soft(apiGetList<LateTask>(fetch, '/infrastructure/schedules/late'))
    ]);
    loaded = true;
    if ($fivesEnabled) {
      const fives = await apiGetData<{ score: number | null }>(fetch, '/modules/fives/five-s').catch(() => null);
      fivesScore = fives?.score ?? null;
    }
  }

  onMount(load);

  const size = (row: Root) => num(row.content_size_bytes ?? row.estimated_size_bytes);
  const measured = (row: Root) => row.content_size_bytes != null || ['done', 'running'].includes(String(row.measure_status ?? ''));
  let totalBytes = $derived(roots.reduce((sum, row) => sum + size(row), 0));
  let totalFiles = $derived(roots.reduce((sum, row) => sum + num(row.content_files), 0));
  // Each figure below is counted by the express search its « See » opens (the same rules as Storage Roots and Insights)
  let failedRoots = $derived(foldersMatching(roots, 'est:mesure-echec'));
  let neverRoots = $derived(roots.filter((row) => !measured(row) && String(row.measure_status ?? '') !== 'failed'));
  let secretRoots = $derived(foldersMatching(roots, 'est:secret'));
  let secretFiles = $derived(secretRoots.reduce((sum, row) => sum + num(row.password_files) + num(row.key_files), 0));
  let quotaRoots = $derived(foldersMatching(roots, 'est:quota-plein'));
  let quotaWaiting = $derived(roots.reduce((sum, row) => sum + num(row.quota_pending_requests), 0));
  let noGuardian = $derived($governanceEnabled ? foldersMatching(roots, 'est:sans-gardien') : []);

  let name = $derived(String(($page.data as any)?.me?.display_name || ($page.data as any)?.me?.username || '').trim());
  // ---- Journal: the day told in one headline and one paragraph, from the figures below ----
  const todayText = formatLongDay();
  const today = todayText.charAt(0).toUpperCase() + todayText.slice(1);
  let lede = $derived([
    t('{count} folder(s) on {servers} server(s)', { count: num(stats.storage_roots) || roots.length, servers: num(stats.storage_endpoints) || endpoints.length }),
    ...(totalBytes ? [t('{size} measured', { size: formatBytes(totalBytes) })] : []),
    ...($governanceEnabled && num(stats.pending_requests) ? [t('{count} request(s) to decide', { count: num(stats.pending_requests) })] : []),
    ...(secretFiles ? [t('{count} file(s) with passwords or keys', { count: secretFiles })] : []),
    ...(failedRoots.length ? [t('{count} measure(s) failed', { count: failedRoots.length })] : [])
  ].join(' · ') + '.');
  let openStory = $state(0);
  // The folders behind a story
  const storyFolders = (key: string): Root[] =>
    (key === 'failed' ? failedRoots : key === 'secrets-files' ? secretRoots : key === 'quota' ? quotaRoots : key === 'guardian' ? noGuardian : key === 'never' ? neverRoots : []).slice(0, 4);
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
      detail: num(stats.stale_pending_requests_count) ? t('{count} waiting for more than {days} days', { count: num(stats.stale_pending_requests_count), days: num(stats.decision_days) || 3 }) : t('at the guardians'), action: t('Decide'), href: num(stats.stale_pending_requests_count) ? '/access-requests?status=pending&overdue=1' : '/access-requests' });
    if (num(stats.open_alerts_count)) list.push({ key: 'alerts', tone: num(stats.critical_alerts_count) ? 'bad' : 'warn', title: t('{count} open alert(s)', { count: num(stats.open_alerts_count) }),
      detail: t('{count} critical or high', { count: num(stats.critical_alerts_count) }), action: t('See'), href: '/observability?tab=alerts&severity=critical_high' });
    if (num(stats.failed_jobs_24h_count)) list.push({ key: 'jobs', tone: 'warn', title: t('{count} failed job(s) in 24 h', { count: num(stats.failed_jobs_24h_count) }),
      detail: t('Directory and file server actions'), action: t('See'), href: '/observability?tab=jobs&status=FAILED' });
    if (failedRoots.length) list.push({ key: 'failed', tone: 'bad', title: t('{count} measure(s) failed', { count: failedRoots.length }),
      detail: failedRoots.slice(0, 3).map((row) => String(row.storage_root_name ?? '')).join(', '), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:mesure-echec')}` });
    if (secretFiles) list.push({ key: 'secrets-files', tone: 'bad', title: t('{count} file(s) with passwords or keys', { count: secretFiles }),
      detail: t('in {count} folder(s)', { count: secretRoots.length }), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:secret')}` });
    if (quotaRoots.length) list.push({ key: 'quota', tone: 'warn', title: t('{count} quota(s) almost full', { count: quotaRoots.length }),
      detail: quotaWaiting ? t('{count} space request(s) waiting', { count: quotaWaiting }) : t('Over the warning threshold of their folder'), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:quota-plein')}` });
    else if (quotaWaiting) list.push({ key: 'quota', tone: 'warn', title: t('{count} space request(s) waiting', { count: quotaWaiting }),
      detail: t('Quotas'), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:quota-demande')}` });
    if (noGuardian.length) list.push({ key: 'guardian', tone: 'warn', title: t('{count} folder(s) without guardian', { count: noGuardian.length }),
      detail: t('Their requests go to the administrators'), action: t('See'), href: `/storage-roots?q=${encodeURIComponent('est:sans-gardien')}` });
    // The same count as Storage Roots (est:non-mesure); the action measures those that can be started now
    if (neverRoots.length) list.push({ key: 'never', tone: 'mut', title: t('{count} folder(s) never measured', { count: foldersMatching(roots, 'est:non-mesure').length }),
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
        <!-- The figures of the data (coverage, availability, recommendations): one place, Insights & Recommendations -->
        <a class="b2s-btn b2s-btn-secondary" href="/insights"><i class="bi bi-speedometer2" aria-hidden="true"></i>{t('Data overview')}</a>
        {#if neverRoots.length}
          <button type="button" class="b2s-btn b2s-btn-primary" disabled={measuring} onclick={measureNever}>
            <i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure {count} folder(s)', { count: neverRoots.length })}
          </button>
        {/if}
      </div>
    </div>
  </div>

  <div class="v2-stats">
    <a class="v2-stat" href="/storage-roots"><i class="bi bi-hdd-network" aria-hidden="true"></i><small>Storage Roots</small><b>{num(stats.storage_roots) || roots.length}</b><span>{t('on {count} server(s)', { count: num(stats.storage_endpoints) || endpoints.length })}</span></a>
    <a class="v2-stat" href="/storage-roots"><i class="bi bi-database" aria-hidden="true"></i><small>{t('Measured volume')}</small><b>{loaded ? formatBytes(totalBytes) : '…'}</b><span>{t('{count} folder(s) measured', { count: roots.length - neverRoots.length - failedRoots.length })}</span></a>
    <a class="v2-stat" href={$fivesEnabled ? '/five-s/explore' : '/storage-roots'}><i class="bi bi-files" aria-hidden="true"></i><small>{t('Files inventoried')}</small><b>{loaded ? totalFiles.toLocaleString('fr-FR') : '…'}</b><span>{t('last measures')}</span></a>
    {#if $fivesEnabled}
      <a class="v2-stat" href="/five-s"><i class="bi bi-stars" aria-hidden="true"></i><small>{t('Average 5S score')}</small><b>{fivesScore ?? '—'}</b><span>{t('on the measured folders')}</span></a>
    {/if}
    {#if $governanceEnabled}
      <a class="v2-stat" href="/access-requests"><i class="bi bi-inbox is-warn" aria-hidden="true"></i><small>{t('Requests to decide')}</small><b>{num(stats.pending_requests)}</b><span>{t('at the guardians')}</span></a>
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
              </div>
            </div>
          {/if}
        </article>
      {:else}
        {#if !loadFailed}<p class="jr-calm">{loaded ? t('Nothing to handle: everything is up to date.') : t('Loading…')}</p>{/if}
      {/each}
      {#if loadFailed}
        <InlineAlert tone="error" compact>
          {t('Part of the platform could not be read: this front page may be incomplete.')}
          {#snippet actions()}<button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={load}>{t('Retry')}</button>{/snippet}
        </InlineAlert>
      {/if}
    </div>
    <aside>
      <ThreadOfTheDay events={activities} seeAll="/observability?tab=audit" empty={t('No problem lately on the platform.')} />
    </aside>
  </div>

</section>

<style>
  .jr-hero { display: block; }
  .jr-kick { color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
  .jr-hero h1 { margin: 10px 0 0; color: var(--b2s-color-heading); font-size: 30px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.15; }
  .jr-hero p { margin: 8px 0 0; max-width: 680px; color: var(--b2s-color-text-muted); font-size: 15px; line-height: 1.5; }
  .jr-acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .jr-body .jr-acts { margin-top: 0; }
  .jr-cols { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 20px; align-items: start; }
  .jr-cols > :is(div, aside) { min-width: 0; padding: 18px 22px; border: 1px solid var(--b2s-color-border-soft); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm); }
  @media (max-width: 1000px) { .jr-cols { grid-template-columns: minmax(0, 1fr); } }
  .jr-h2 { display: flex; align-items: baseline; gap: 12px; margin: 0 0 10px; color: var(--b2s-color-heading); font-size: 18px; font-weight: 700; letter-spacing: -0.025em; }
  .jr-h2 :global(.b2s-link-btn) { margin-left: auto; font-size: 13px; letter-spacing: 0; }
  .jr-story { border-top: 1px solid var(--b2s-color-border-soft); }
  .jr-sh { width: 100%; display: grid; grid-template-columns: 56px minmax(0, 1fr) 28px; gap: 16px; align-items: start; padding: 20px 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .jr-sh:focus-visible { outline: 2px solid var(--b2s-accent-vivid); outline-offset: 2px; }
  .jr-idx { color: var(--b2s-color-border); font-size: 28px; font-weight: 800; line-height: 1; }
  .jr-sh h3 { margin: 0; font-size: 19px; font-weight: 600; letter-spacing: -0.015em; }
  .jr-sh p { margin: 6px 0 10px; color: var(--b2s-color-text-soft); line-height: 1.5; }
  .jr-plus { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--b2s-color-border); border-radius: 50%; transition: transform var(--b2s-motion-base) var(--b2s-ease-out); }
  .jr-plus.open { transform: rotate(45deg); border-color: var(--b2s-accent); background: var(--b2s-accent); color: #fff; }
  .jr-body { display: flex; flex-direction: column; gap: 12px; padding: 0 0 22px 72px; }
  .jr-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
  .jr-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px dashed var(--b2s-color-border-soft); }
  .jr-list a { color: inherit; font-weight: 600; text-decoration: none; }
  .jr-list a:hover { color: var(--b2s-color-text-soft); text-decoration: underline; }
  .jr-list span { color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: 12px; }
  .jr-calm { color: var(--b2s-color-text-muted); }
  .v2-cols.is-single { grid-template-columns: minmax(0, 1fr); }
  .dash__av { width: 30px; height: 30px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--b2s-color-surface-muted);
    color: var(--b2s-color-heading); font-size: 11px; font-weight: 700; }
</style>
