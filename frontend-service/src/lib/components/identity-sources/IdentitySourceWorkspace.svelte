<script lang="ts">
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { apiGetData, apiGetList } from '$lib/api/client';
  import { getHealthSummary, type HealthSummaryDay } from '$lib/api/health';
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';
  import EntityHeroCard from '$lib/components/entity/EntityHeroCard.svelte';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import { t } from '$lib/i18n';
  import type { IdentitySourceCardVM } from '$lib/mappers/identity-sources.mapper';
  import { timeAgo } from '$lib/utils/format';

  /**
   * One directory, as a page: identity card, figures, « to do », then Overview · Inventory · Synchronisation ·
   * Connection · Activity. Same grammar as the Servers and Folders pages.
   */
  export let card: IdentitySourceCardVM;
  export let internal: Record<string, any> | null = null;
  export let probeRunning = false;
  export let snapshotRunning = false;
  export let busy = false;
  export let onEdit: () => void = () => {};
  export let onTest: () => void = () => {};
  export let onSync: () => void = () => {};
  export let onToggle: () => void = () => {};
  export let onDelete: () => void = () => {};

  type Overview = {
    users: number; users_with_email: number; groups: number; governed_groups: number;
    governed_sample: Array<{ name: string; dn: string; members: number }>;
    endpoints: Array<{ id: number; name: string; endpoint_type: string; host: string; roots: number }>;
  };
  let overview: Overview | null = null;
  let health: HealthSummaryDay[] = [];
  let activity: any[] = [];
  let tab = 'overview';
  let loadedFor = 0;

  $: raw = (card?.raw ?? {}) as Record<string, any>;
  $: if (card && card.id !== loadedFor) load(card.id);

  async function load(id: number) {
    loadedFor = id;
    overview = null;
    health = [];
    activity = [];
    inventory = [];
    inventoryFor = '';
    tab = 'overview';
    const [o, h, a] = await Promise.all([
      apiGetData<Overview>(fetch, `/identity-sources/${id}/overview`).catch(() => null),
      getHealthSummary(fetch, 'identity_source', id, 14).catch(() => []),
      apiGetList<any>(fetch, '/activity/by-target', { target_type: 'identity_source', target_id: id, limit: 80 }).catch(() => [])
    ]);
    if (loadedFor !== id) return;
    overview = o;
    health = h;
    activity = a;
  }

  // Identity card
  const TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = { success: 'success', warning: 'warning', error: 'danger', danger: 'danger' };
  $: endpointUrl = raw.host ? `${String(raw.protocol || 'ldaps')}://${raw.host}${raw.port ? `:${raw.port}` : ''}` : '';
  $: chips = [
    raw.domain_name ? { label: t('Domain {domain}', { domain: raw.domain_name }) } : null,
    raw.base_dn ? { label: String(raw.base_dn), mono: true } : null,
    card.bindDn && card.bindDn !== '—' ? { label: t('Read account {account}', { account: card.bindDn }), icon: 'bi-person-badge' } : null,
    card.supportsProbe ? { label: raw.tls_verify ? t('Certificate verified') : t('Certificate not verified'), icon: raw.tls_verify ? 'bi-shield-check' : 'bi-shield-exclamation' } : null,
    { label: raw.auth_enabled ? t('Sign-in of its users: on') : t('Sign-in of its users: off'), icon: 'bi-box-arrow-in-right' }
  ].filter(Boolean) as Array<{ label: string; icon?: string; mono?: boolean }>;
  $: actions = [
    { key: 'edit', label: t('Edit'), icon: 'bi-pencil', variant: 'secondary', disabled: card.isLocal, onClick: onEdit },
    ...(card.supportsProbe ? [{ key: 'test', label: probeRunning ? t('Testing…') : t('Test the connection'), icon: 'bi-plug', variant: 'secondary', disabled: probeRunning || busy, onClick: onTest }] : []),
    ...(card.supportsSnapshot ? [{ key: 'sync', label: snapshotRunning ? t('Synchronizing…') : t('Synchronize'), icon: 'bi-arrow-repeat', variant: 'primary', disabled: snapshotRunning || busy, onClick: onSync }] : []),
    { key: 'toggle', label: card.isEnabled ? t('Disable') : t('Enable'), icon: card.isEnabled ? 'bi-pause-circle' : 'bi-play-circle', overflow: true, onClick: onToggle },
    { key: 'delete', label: t('Delete'), icon: 'bi-trash', variant: 'danger', overflow: true, onClick: onDelete }
  ] as EntityActionItem[];

  // To do
  $: failed = card.healthTone === 'error';
  $: steps = [
    ...(!card.isEnabled ? [{ key: 'off', tone: 'info' as const, icon: 'bi-pause-circle', title: t('This directory is disabled'), detail: t('Its users cannot sign in and it is no longer synchronized.'), label: t('Enable'), run: onToggle }] : []),
    ...(card.isEnabled && failed ? [{ key: 'probe', tone: 'bad' as const, icon: 'bi-plug', title: t('The last connection test failed'), detail: String(internal?.last_probe_message ?? raw.last_probe_message ?? ''), label: t('Edit the connection'), run: onEdit }] : []),
    ...(card.isEnabled && !failed && card.supportsProbe && (card.lastProbeStale || !raw.last_probe_at)
      ? [{ key: 'stale', tone: 'warn' as const, icon: 'bi-clock-history', title: raw.last_probe_at ? t('Connection not tested for {age}', { age: timeAgo(raw.last_probe_at).replace(/^il y a /, '') }) : t('Connection never tested'), detail: t('The synchronization may pass while the full test (bind, certificate, search) has not been run again.'), label: t('Test the connection'), busy: probeRunning, run: onTest }]
      : []),
    ...(card.isEnabled && card.supportsSnapshot && card.neverSynced ? [{ key: 'never', tone: 'warn' as const, icon: 'bi-cloud-arrow-down', title: t('Never synchronized'), detail: t('No user or group read yet: requests cannot target its people.'), label: t('Synchronize'), busy: snapshotRunning, run: onSync }] : []),
    ...(card.isEnabled && card.supportsSnapshot && !card.neverSynced && card.snapshotTone === 'error' ? [{ key: 'snap', tone: 'bad' as const, icon: 'bi-cloud-slash', title: t('The last synchronization failed'), detail: card.snapshotLabel, label: t('Synchronize'), busy: snapshotRunning, run: onSync }] : [])
  ] as EntityTodoStep[];

  // Figures
  $: smb = (overview?.endpoints ?? []).filter((ep) => ep.endpoint_type !== 'dfs');
  $: dfs = (overview?.endpoints ?? []).filter((ep) => ep.endpoint_type === 'dfs');
  $: dfsServers = [...new Set(dfs.map((ep) => String(ep.host || '').split('.')[0].toUpperCase()))].map((server) => ({ server, namespaces: dfs.filter((ep) => String(ep.host || '').split('.')[0].toUpperCase() === server) }));
  $: tiles = [
    { key: 'users', label: t('Users'), value: overview?.users ?? card.usersCount, hint: overview ? t('{count} with an e-mail', { count: overview.users_with_email }) : '', go: () => openInventory('users') },
    { key: 'groups', label: t('Groups'), value: overview?.groups ?? card.groupsCount, hint: overview ? t('{count} governed by BornToShare', { count: overview.governed_groups }) : '', go: () => openInventory('groups') },
    { key: 'members', label: t('Memberships'), value: card.membershipsCount, hint: t('user ↔ group'), go: () => openInventory('users') },
    { key: 'servers', label: t('Linked servers'), value: overview?.endpoints.length ?? null, hint: overview ? t('{smb} file server(s) · {dfs} DFS namespace(s)', { smb: smb.length, dfs: dfs.length }) : '', go: () => (tab = 'overview') }
  ];

  // Health strip (14 days)
  const DAY_TONE: Record<string, string> = { success: 'ok', warning: 'warn', failed: 'bad', running: 'run' };
  $: strip = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(Date.now() - (13 - index) * 86400000).toISOString().slice(0, 10);
    const day = health.find((item) => String(item.date).slice(0, 10) === date);
    return { date, tone: day ? DAY_TONE[String(day.status)] ?? 'none' : 'none', title: day ? `${date} · ${day.checks} ${t('check(s)')}${day.failures ? ` · ${day.failures} ${t('failure(s)')}` : ''}` : `${date} · ${t('no check')}` };
  });

  // Inventory
  let inventoryKind: 'users' | 'groups' = 'users';
  let inventoryFilter = 'all';
  let inventoryQuery = '';
  let inventory: any[] = [];
  let inventoryLoading = false;
  let inventoryFor = '';
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  function openInventory(kind: 'users' | 'groups') {
    inventoryKind = kind;
    inventoryFilter = 'all';
    tab = 'inventory';
  }
  $: if (tab === 'inventory' && card && `${card.id}:${inventoryKind}:${inventoryQuery}` !== inventoryFor) queueInventory();
  function queueInventory() {
    if (searchTimer) clearTimeout(searchTimer);
    const key = `${card.id}:${inventoryKind}:${inventoryQuery}`;
    inventoryFor = key;
    searchTimer = setTimeout(async () => {
      inventoryLoading = true;
      try {
        const rows = await apiGetList<any>(fetch, `/identity-sources/${card.id}/inventory`, { kind: inventoryKind, q: inventoryQuery.trim(), limit: 300 });
        if (inventoryFor === key) inventory = rows;
      } catch {
        if (inventoryFor === key) inventory = [];
      } finally {
        inventoryLoading = false;
      }
    }, inventoryQuery ? 300 : 0);
  }
  $: hasMail = (row: any) => Boolean(String(row?.email ?? '').trim());
  $: shownRows = inventory.filter((row) =>
    inventoryFilter === 'all' ||
    (inventoryKind === 'users' ? (inventoryFilter === 'people' ? hasMail(row) : !hasMail(row)) : inventoryFilter === 'governed' ? row.governed : !row.governed)
  );
  $: filterOptions = inventoryKind === 'users'
    ? [{ key: 'all', label: t('All'), count: inventory.length }, { key: 'people', label: t('People'), count: inventory.filter(hasMail).length }, { key: 'tech', label: t('Technical accounts'), count: inventory.filter((row) => !hasMail(row)).length }]
    : [{ key: 'all', label: t('All'), count: inventory.length }, { key: 'governed', label: t('Governed by BornToShare'), count: inventory.filter((row) => row.governed).length }, { key: 'other', label: t('Others'), count: inventory.filter((row) => !row.governed).length }];
  const isModify = (name: string) => /_RW$/i.test(String(name));
  const initials = (value: string) => String(value || '?').split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('');

  $: tabs = [
    { key: 'overview', label: t('Overview') },
    ...(card.supportsSnapshot ? [{ key: 'inventory', label: t('Inventory'), count: (overview?.users ?? 0) + (overview?.groups ?? 0) || null }] : []),
    { key: 'activity', label: t('Activity'), count: activity.length || null }
  ];
  $: facts = [
    { label: t('Server'), value: raw.host ? `${raw.host}${raw.port ? ` · ${t('port')} ${raw.port}` : ''}` : '—', mono: true },
    { label: t('Protocol'), value: String(raw.protocol || '—').toUpperCase() },
    { label: t('Search base'), value: raw.base_dn || '—', mono: true },
    { label: t('Read account'), value: card.bindDn || '—', mono: true },
    { label: t('Certificate'), value: raw.tls_verify ? t('Verified') : t('Not verified') },
    { label: t('Last test'), value: t('Never'), time: raw.last_probe_at || null, warn: Boolean(card.lastProbeStale || !raw.last_probe_at) }
  ] as Array<{ label: string; value: string; mono?: boolean; warn?: boolean; time?: string | null }>;
</script>

<div class="isw">
  <EntityHeroCard icon={card.isLocal ? 'bi-person-lock' : 'bi-diagram-3'} iconTone={card.isLocal ? 'neutral' : 'blue'}
    crumbs={[t('Directories'), card.typeLabel]} title={card.name} statusLabel={card.healthLabel} statusTone={TONE[String(card.healthTone)] ?? 'neutral'}
    path={endpointUrl} {chips} {actions} actionsAriaLabel={t('Identity source actions')} />

  {#if card.supportsSnapshot}
    <div class="b2s-stat-tiles isw__tiles">
      {#each tiles as tile (tile.key)}
        <button type="button" class="b2s-stat-tile" on:click={tile.go}>
          <span>{tile.label}</span>
          <b>{tile.value ?? '—'}</b>
          <small>{tile.hint}</small>
        </button>
      {/each}
    </div>
  {/if}

  {#if steps.length}<EntityTodoCard title={t('To do on this directory')} {steps} />{/if}

  <Tabs {tabs} activeKey={tab} onChange={(key) => (tab = key)} ariaLabel={t('Sections')} />

  {#if tab === 'overview'}
    <div class="isw__grid">
      <div class="isw__col">
        {#if card.supportsSnapshot}
          <section class="isw__card" aria-label={t('Synchronization')}>
            <header><h2>{t('Synchronization')}</h2><small>{t('Last 14 days')}</small></header>
            <div class="isw__strip" role="img" aria-label={t('Health of the last 14 days')}>
              {#each strip as day (day.date)}<span class={`is-${day.tone}`} title={day.title}></span>{/each}
            </div>
            <div class="isw__trio">
              <div><span>{t('Last')}</span><b><RelativeTime value={raw.last_snapshot_at} empty={t('Never')} /></b></div>
              <div><span>{t('Read')}</span><b>{t('{users} users · {groups} groups', { users: overview?.users ?? card.usersCount ?? 0, groups: overview?.groups ?? card.groupsCount ?? 0 })}</b></div>
              <div><span>{t('Schedule')}</span><a href="/admin/advanced-settings/infrastructure">{t('Settings › Schedules')}</a></div>
            </div>
          </section>
        {/if}
      </div>
      <div class="isw__col">
        {#if card.supportsProbe}
          <section class="isw__card" aria-label={t('Connection')}>
            <header><h2>{t('Connection')}</h2><button type="button" class="b2s-link-btn" on:click={onEdit}>{t('Edit')}</button></header>
            <dl class="isw__facts">
              {#each facts as fact (fact.label)}<dt>{fact.label}</dt><dd class:mono={fact.mono} class:is-warn={fact.warn}>{#if fact.time}<RelativeTime value={fact.time} />{:else}{fact.value}{/if}</dd>{/each}
              <dt>{t('Authentication')}</dt><dd>{raw.capabilities?.auth_mode === 'kerberos' ? 'Kerberos' : 'NTLM'}</dd>
              {#if internal?.last_probe_message ?? raw.last_probe_message}<dt>{t('Last message')}</dt><dd>{internal?.last_probe_message ?? raw.last_probe_message}</dd>{/if}
            </dl>
          </section>
        {/if}
      </div>
    </div>
  {:else if tab === 'inventory'}
    <div class="isw__tools">
      <SegmentedFilter ariaLabel={t('Kind of object')} value={inventoryKind}
        onChange={(key) => { inventoryKind = key === 'groups' ? 'groups' : 'users'; inventoryFilter = 'all'; }}
        options={[{ key: 'users', label: t('Users'), count: overview?.users }, { key: 'groups', label: t('Groups'), count: overview?.groups }]} />
      <SegmentedFilter ariaLabel={t('Filter')} bind:value={inventoryFilter} options={filterOptions} />
      <input class="b2s-input isw__search" type="search" bind:value={inventoryQuery} aria-label={t('Search the inventory')}
        placeholder={inventoryKind === 'users' ? t('Name, login, e-mail…') : t('Name or DN of the group…')} />
    </div>
    <section class="isw__card isw__table" aria-label={t('Inventory')}>
      {#if inventoryLoading && !inventory.length}
        <LoadingState skeleton="rows" rows={8} />
      {:else if !shownRows.length}
        <EmptyStateInline message={t('Nothing matches in the last reading.')} />
      {:else if inventoryKind === 'users'}
        <div class="isw__thead isw__u" aria-hidden="true"><span>{t('Name')}</span><span>{t('Login')}</span><span>{t('E-mail')}</span><span>{t('Groups')}</span></div>
        {#each shownRows as row (row.id)}
          <div class="isw__trow isw__u">
            <span class="isw__who"><span class="isw__av" class:is-tech={!hasMail(row)}>{initials(row.display_name || row.username)}</span><span title={row.dn}>{row.display_name || row.username}</span></span>
            <span class="mono">{row.username}</span>
            <span class:is-warn={!hasMail(row)}>{hasMail(row) ? row.email : t('no e-mail')}</span>
            <span class="num">{row.groups}</span>
          </div>
        {/each}
      {:else}
        <div class="isw__thead isw__g" aria-hidden="true"><span>{t('Group')}</span><span>{t('Description')}</span><span>{t('Members')}</span></div>
        {#each shownRows as row (row.id)}
          <div class="isw__trow isw__g">
            <span class="isw__who"><i class={`bi ${row.governed ? 'bi-shield-check' : 'bi-people'}`} aria-hidden="true"></i><code title={row.dn}>{row.name}</code></span>
            <span class="isw__muted">{row.description || '—'}</span>
            <span class="num">{row.members}</span>
          </div>
        {/each}
      {/if}
      {#if inventory.length >= 300}<p class="isw__muted isw__more">{t('First 300 shown: search to narrow.')}</p>{/if}
    </section>
    {#if inventoryKind === 'users' && overview && overview.users > overview.users_with_email}
      <p class="isw__note"><i class="bi bi-info-circle" aria-hidden="true"></i>{t('{count} account(s) without an e-mail: technical or administration accounts. They receive neither requests nor notices.', { count: overview.users - overview.users_with_email })}</p>
    {/if}
  {:else}
    <section class="isw__card" aria-label={t('Activity')}>
      <ActivityTimeline items={activity} emptyLabel={t('No activity for this directory yet.')} />
    </section>
  {/if}
</div>

<style>
  .isw { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .isw__tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .isw__tiles .b2s-stat-tile { text-align: left; border: 1px solid var(--b2s-color-border); cursor: pointer; font: inherit; color: inherit; }
  .isw__tiles .b2s-stat-tile > span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .isw__tiles .b2s-stat-tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .isw__grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 16px; align-items: start; }
  .isw__col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .isw__card { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .isw__card > header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .isw__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .isw__card header small, .isw__muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .isw__muted { margin: 0; }
  .isw__strip { display: grid; grid-template-columns: repeat(14, minmax(0, 1fr)); gap: 4px; }
  .isw__strip span { height: 26px; border-radius: 5px; background: var(--b2s-color-neutral-soft); }
  .isw__strip .is-ok { background: #2f9e5b; }
  .isw__strip .is-warn { background: #d68a00; }
  .isw__strip .is-bad { background: #c0392b; }
  .isw__strip .is-run { background: #3b6fd8; }
  .isw__trio { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; font-size: var(--b2s-fs-sm); }
  .isw__trio div { display: flex; flex-direction: column; gap: 2px; }
  .isw__trio span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .isw__trio b { font-weight: 600; }
  .isw__rows { display: flex; flex-direction: column; }
  .isw__row { display: grid; grid-template-columns: minmax(0, 1fr) 110px 90px; gap: 12px; align-items: center; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); }
  .isw__lvl { justify-self: start; padding: 2px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .isw__lvl.is-rx { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .isw__lvl.is-rw { background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); }
  .isw__facts { display: grid; grid-template-columns: 160px minmax(0, 1fr); margin: 0; font-size: var(--b2s-fs-sm); }
  .isw__facts dt, .isw__facts dd { margin: 0; padding: 8px 0; border-top: 1px solid var(--b2s-color-border); }
  .isw__facts dt { color: var(--b2s-color-text-muted); }
  .isw__facts dd { min-width: 0; overflow-wrap: anywhere; }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .is-warn { color: var(--b2s-color-warning-strong, #9a5b00); font-weight: 600; }
  .isw__link { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); color: inherit; text-decoration: none; }
  .isw__link:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .isw__tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .isw__search { margin-left: auto; width: 320px; }
  .isw__table { padding: 0; gap: 0; overflow: hidden; }
  .isw__thead, .isw__trow { display: grid; gap: 12px; align-items: center; padding: 9px 16px; font-size: var(--b2s-fs-sm); }
  .isw__u { grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1.4fr) 70px; }
  .isw__g { grid-template-columns: minmax(0, 1.3fr) minmax(0, 1.5fr) 80px; }
  .isw__thead { background: var(--b2s-color-surface-soft, #f6f7f9); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .isw__trow { border-top: 1px solid var(--b2s-color-border); }
  .isw__trow > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .isw__trow code { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text); }
  .isw__who { display: flex; align-items: center; gap: 10px; }
  .isw__av { flex: 0 0 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 11px; font-weight: 600; }
  .isw__av.is-tech { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .isw__more { padding: 10px 16px; border-top: 1px solid var(--b2s-color-border); }
  .isw__note { display: flex; gap: 8px; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .isw__btns { display: flex; gap: 8px; }
</style>
