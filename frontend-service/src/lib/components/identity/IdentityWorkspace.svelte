<script lang="ts">
  
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { apiGetList } from '$lib/api/client';
  import { getIdentityOverview, type IdentityOverview } from '$lib/api/identity';
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import EntityHeroCard from '$lib/components/entity/EntityHeroCard.svelte';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import IdentitySubstitutes from '$lib/components/identity/IdentitySubstitutes.svelte';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { timeAgo } from '$lib/utils/format';

  
  
  
  interface Props {
    /**
   * One person, as a page: identity card with the role as a switch (undo for a few seconds), « to do », figures,
   * then what they guard (map by share, sole guardian folders, co-guardians), their requests and the activity.
   */
    item: Record<string, any>;
    canDelete?: boolean;
    /** The signed-in person: no demotion, disabling or deletion of one's own account */
    isSelf?: boolean;
    busy?: boolean;
    onSetRole?: (role: 'user' | 'platform_admin') => Promise<boolean>;
    onToggleActive?: () => void;
    onEdit?: () => void;
    onDelete?: () => void;
    /** Everyone, to pick a backup guardian */
    people?: Array<Record<string, any>>;
  }

  let {
    item,
    canDelete = true,
    isSelf = false,
    busy = false,
    onSetRole = async () => false,
    onToggleActive = () => {},
    onEdit = () => {},
    onDelete = () => {},
    people = []
  }: Props = $props();

  let data: IdentityOverview | null = $state(null);
  let activity: any[] = $state([]);
  let loadedFor = $state(0);
  let tab = $state('overview');
  let shareFilter = $state('all');

  async function load(identityId: number) {
    loadedFor = identityId;
    data = null;
    activity = [];
    tab = 'overview';
    shareFilter = 'all';
    const [overview, onIt, byIt] = await Promise.all([
      getIdentityOverview(fetch, identityId).catch(() => null),
      apiGetList<any>(fetch, '/activity/by-target', { target_type: 'identity', target_id: identityId, limit: 60 }).catch(() => []),
      apiGetList<any>(fetch, '/activity/by-actor', { actor_id: identityId, limit: 60 }).catch(() => [])
    ]);
    if (loadedFor !== identityId) return;
    data = overview;
    const seen = new Set<string>();
    activity = [...onIt, ...byIt]
      .filter((event) => { const key = String(event?.id ?? JSON.stringify(event)); if (seen.has(key)) return false; seen.add(key); return true; })
      .sort((a, b) => String(b?.created_at ?? b?.event_time ?? '').localeCompare(String(a?.created_at ?? a?.event_time ?? '')));
  }
  export const reload = () => id && load(id);

  async function setRole(role: 'user' | 'platform_admin') {
    if (busy || adminByGroupOnly || (role === 'platform_admin') === isAdmin) return;
    const previous: 'user' | 'platform_admin' = isAdmin ? 'platform_admin' : 'user';
    if (!(await onSetRole(role))) return;
    await load(id);
    toast.success(role === 'platform_admin' ? t('{name} is now an administrator.', { name: displayName }) : t('{name} is a user again.', { name: displayName }), {
      action: { label: t('Undo'), run: async () => { if (await onSetRole(previous)) await load(id); } }
    });
  }





  const REQUEST_TONES: Record<string, string> = { approved: '#2f9e5b', applied: '#2f9e5b', active: '#2f9e5b', pending: '#3b6fd8', revoked: '#8a93a3', rejected: '#c0392b', cancelled: '#cdd2db', expired: '#b9c0cc' };
  const REQUEST_LABEL = (): Record<string, string> => ({ approved: t('approved'), applied: t('applied'), active: t('active'), pending: t('pending'), revoked: t('revoked'), rejected: t('rejected'), cancelled: t('cancelled'), expired: t('expired') });

  let id = $derived(Number(item?.id ?? 0));
  $effect.pre(() => {
    if (id && id !== loadedFor) load(id);
  });
  // Role: held directly (switchable) or through a directory group (shown, not switchable here)
  let adminVia = $derived((data?.roles ?? []).filter((role) => role.code === 'platform_admin').map((role) => role.via));
  let isAdmin = $derived(adminVia.length > 0);
  let adminByGroupOnly = $derived(isAdmin && !adminVia.includes('direct'));
  let displayName = $derived(String(data?.display_name || item?.display_name || item?.username || '—'));
  let initials = $derived(displayName.split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?');
  let local = $derived(String(data?.auth_source ?? item?.auth_source ?? '') === 'local');
  let hasMail = $derived(Boolean(String(data?.email ?? item?.email ?? '').trim()));
  let active = $derived(data ? data.is_active : item?.is_active !== false);
  // Disabled by the synchronization: the user is no longer in the directory (enabled again if it comes back)
  let leftDirectory = $derived(!active && String((data as any)?.status ?? (item as any)?.status ?? '') === 'left_directory');
  let guarded = $derived(data?.guarded ?? []);
  let sole = $derived(guarded.filter((folder) => folder.sole));
  let requestsTotal = $derived(Object.values(data?.requests ?? {}).reduce((sum, value) => sum + Number(value || 0), 0));
  let actions = $derived([
    { key: 'edit', label: t('Edit'), icon: 'bi-pencil', variant: 'secondary', onClick: onEdit },
    ...(isSelf ? [] : [
      { key: 'toggle', label: active ? t('Disable') : t('Enable'), icon: active ? 'bi-pause-circle' : 'bi-play-circle', overflow: true, onClick: onToggleActive },
      { key: 'delete', label: t('Delete'), icon: 'bi-trash', variant: 'danger', overflow: true, disabled: !canDelete, onClick: onDelete }
    ])
  ] as EntityActionItem[]);
  let steps = $derived([
    ...(!active && guarded.length ? [{ key: 'off', tone: 'bad' as const, icon: 'bi-pause-circle', title: t('Disabled, but guardian of {count} folder(s)', { count: guarded.length }), detail: t('Its requests wait for the other guardians or an administrator.'), label: t('Enable'), run: onToggleActive }] : []),
    ...(active && guarded.length && !hasMail ? [{ key: 'mail', tone: 'warn' as const, icon: 'bi-envelope-slash', title: t('{count} folder(s) wait for their validations, but there is no e-mail', { count: guarded.length }), detail: local ? t('Neither requests nor reminders reach them. Add an e-mail address.') : t('Neither requests nor reminders reach them. Fill the mail attribute in the directory: it is read again at the next synchronization.'), label: local ? t('Edit') : t('See the folders'), run: local ? onEdit : () => (tab = 'guarded') }] : []),
    ...(sole.length ? [{ key: 'sole', tone: 'info' as const, icon: 'bi-person-exclamation', title: t('Only guardian of {count} folder(s)', { count: sole.length }), detail: t('Without them, only an administrator validates the requests of these folders.'), label: t('See them'), run: () => { tab = 'guarded'; shareFilter = 'sole'; } }] : [])
  ] as EntityTodoStep[]);
  // Map of what they guard: one tile per share, one cell per folder (red: only guardian)
  let shares = $derived([...guarded.reduce((map, folder) => {
    const key = folder.share || '—';
    if (!map.has(key)) map.set(key, { share: key, folders: [] as typeof guarded });
    map.get(key)!.folders.push(folder);
    return map;
  }, new Map<string, { share: string; folders: typeof guarded }>()).values()].sort((a, b) => b.folders.length - a.folders.length || a.share.localeCompare(b.share, 'fr')));
  let shownShares = $derived(shares.slice(0, 20));
  let shareChips = $derived([
    { key: 'all', label: t('All'), count: guarded.length },
    ...(sole.length ? [{ key: 'sole', label: t('Only guardian'), count: sole.length }] : []),
    ...shares.slice(0, 8).map((share) => ({ key: `share:${share.share}`, label: share.share, count: share.folders.length }))
  ]);
  let rows = $derived(guarded.filter((folder) => shareFilter === 'all' || (shareFilter === 'sole' ? folder.sole : `share:${folder.share}` === shareFilter)));
  let requestParts = $derived(Object.entries(data?.requests ?? {}).filter(([, count]) => Number(count) > 0).sort((a, b) => Number(b[1]) - Number(a[1])));
  let tabs = $derived([
    { key: 'overview', label: t('Overview') },
    { key: 'guarded', label: t('Guarded folders'), count: guarded.length || null },
    { key: 'activity', label: t('Activity'), count: activity.length || null }
  ]);
</script>

<div class="iw">
  <EntityHeroCard
    avatar={initials} avatarRing={active && !local} avatarOff={!active}
    crumbs={[t('Identities'), String(data?.source_name ?? item?.source_name ?? '')]}
    title={displayName}
    statusLabel={active ? t('Active') : leftDirectory ? t('Left the directory') : t('Disabled')} statusTone={active ? 'success' : leftDirectory ? 'warning' : 'neutral'}
    path={String(data?.dn ?? '')}
    chips={[
      ...(!data?.dn && (data?.username || item?.username) ? [{ label: String(data?.username ?? item?.username), mono: true }] : []),
      hasMail ? { label: String(data?.email ?? item?.email) } : { label: t('No e-mail address'), tone: 'warning' as const },
      ...(adminByGroupOnly ? [{ label: t('Administrator through a directory group'), icon: 'bi-people' }] : [])
    ]}
    {actions} actionsAriaLabel={t('Identity actions')}>
    {#snippet noteContent()}
        {#if data?.updated_at}{t('updated')} <RelativeTime value={data.updated_at} />{/if}
      {/snippet}
    {#snippet side()}
      
        <div class="iw__seg" role="radiogroup" aria-label={t('Role in BornToShare')}>
          <button type="button" role="radio" aria-checked={!isAdmin} class:is-on={!isAdmin} disabled={busy || adminByGroupOnly || !data || (isSelf && isAdmin)} title={isSelf && isAdmin ? t('You cannot demote your own account.') : undefined} onclick={() => setRole('user')}>{t('User')}</button>
          <button type="button" role="radio" aria-checked={isAdmin} class:is-on={isAdmin} disabled={busy || adminByGroupOnly || !data} onclick={() => setRole('platform_admin')}>{t('Administrator')}</button>
        </div>
        {#if guarded.length}<small class="iw__plus">{t('+ guardian of {count} folder(s)', { count: guarded.length })}</small>{/if}
      
      {/snippet}
  </EntityHeroCard>

  {#if !data}
    <LoadingState block skeleton="detail" />
  {:else}
    <div class="b2s-stat-tiles iw__tiles">
      <div class="b2s-stat-tile"><span>{t('Role')}</span><b>{isAdmin ? t('Administrator') : guarded.length ? t('Guardian') : t('User')}</b><small>{isAdmin && guarded.length ? t('and guardian') : guarded.length ? t('and user') : ''}</small></div>
      <button type="button" class="b2s-stat-tile" onclick={() => (tab = 'guarded')}><span>{t('Guarded folders')}</span><b><CountUp value={Number(guarded.length)} /></b><small>{sole.length ? t('{count} as only guardian', { count: sole.length }) : t('always with another guardian')}</small></button>
      <div class="b2s-stat-tile"><span>{t('Accesses in progress')}</span><b><CountUp value={Number(data.active_accesses)} /></b><small>{data.active_accesses ? '' : t('no folder open for them')}</small></div>
      <div class="b2s-stat-tile"><span>{t('Requests')}</span><b><CountUp value={Number(requestsTotal)} /></b><small>{requestParts.map(([status, count]) => `${count} ${REQUEST_LABEL()[status] ?? status}`).join(' · ')}</small></div>
    </div>

    {#if steps.length}<EntityTodoCard title={t('To do on this identity')} {steps} />{/if}

    <Tabs {tabs} activeKey={tab} onChange={(key) => (tab = key)} ariaLabel={t('Sections')} />

    {#if tab === 'overview'}
      <div class="iw__grid">
        <section class="iw__card" aria-label={t('What they guard')}>
          <header><h2>{t('What they guard')}</h2><small>{t('{folders} folder(s) · {shares} share(s)', { folders: guarded.length, shares: shares.length })}</small></header>
          {#if guarded.length}
            <div class="iw__map">
              {#each shownShares as share (share.share)}
                <button type="button" class="iw__site" title={t('{share}: {count} folder(s)', { share: share.share, count: share.folders.length })} onclick={() => { tab = 'guarded'; shareFilter = `share:${share.share}`; }}>
                  <span class="iw__site-head"><b>{share.share}</b><span>{share.folders.length}</span></span>
                  <span class="iw__cells" aria-hidden="true">{#each share.folders.slice(0, 20) as folder (folder.id)}<span class="iw__cell" class:is-sole={folder.sole}></span>{/each}</span>
                </button>
              {/each}
            </div>
            {#if shares.length > shownShares.length}<small class="iw__muted">{t('+ {count} other share(s)', { count: shares.length - shownShares.length })}</small>{/if}
            {#if sole.length}
              <div class="iw__sole">
                <span class="iw__key is-sole" aria-hidden="true"></span>
                <span><b>{t('Only guardian of {count} folder(s)', { count: sole.length })}</b> : {sole.slice(0, 4).map((folder) => `${folder.name} (${folder.share})`).join(', ')}{sole.length > 4 ? '…' : ''}</span>
              </div>
            {/if}
            <div class="iw__legend"><span><span class="iw__key" aria-hidden="true"></span>{t('guarded with someone else')}</span><span><span class="iw__key is-sole" aria-hidden="true"></span>{t('only guardian')}</span></div>
          {:else}
            <EmptyStateInline message={t('Guardian of no folder.')} />
          {/if}
        </section>

        <div class="iw__col">
          <IdentitySubstitutes identityId={id} isGuardian={guarded.length > 0} {people} onChanged={() => load(id)} />
          {#if data.co_guardians.length}
            <section class="iw__card" aria-label={t('Guards with')}>
              <header><h2>{t('Guards with')}</h2></header>
              {#each data.co_guardians.slice(0, 4) as partner (partner.id)}
                <div class="iw__partner">
                  <span class="iw__mini">{partner.name.split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('')}</span>
                  <span><b>{partner.name}</b><small>{t('{count} folder(s) in common', { count: partner.shared })}{partner.has_email ? '' : ` · ${t('no e-mail either')}`}</small></span>
                </div>
              {/each}
              {#if !hasMail && data.co_guardians.length && data.co_guardians.every((partner) => !partner.has_email)}
                <p class="iw__muted">{t('None of them receives the requests by e-mail: they are only seen in BornToShare.')}</p>
              {/if}
            </section>
          {/if}
          <section class="iw__card" aria-label={t('Their requests')}>
            <header><h2>{t('Their requests')}</h2><small>{data.active_accesses ? t('{count} access(es) in progress', { count: data.active_accesses }) : t('no access in progress')}</small></header>
            {#if requestsTotal}
              <div class="iw__bar" role="img" aria-label={requestParts.map(([status, count]) => `${count} ${REQUEST_LABEL()[status] ?? status}`).join(', ')}>
                {#each requestParts as [status, count] (status)}<span style={`flex:${count};background:${REQUEST_TONES[status] ?? '#8a93a3'}`}></span>{/each}
              </div>
              <div class="iw__legend">
                {#each requestParts as [status, count] (status)}<span><span class="iw__key" style={`background:${REQUEST_TONES[status] ?? '#8a93a3'}`} aria-hidden="true"></span>{count} {REQUEST_LABEL()[status] ?? status}</span>{/each}
              </div>
            {:else}
              <EmptyStateInline message={t('No request yet.')} />
            {/if}
          </section>
        </div>
      </div>
    {:else if tab === 'guarded'}
      <div class="iw__chipsbar" role="group" aria-label={t('Filter the folders')}>
        {#each shareChips as chip (chip.key)}
          <button type="button" class:is-on={shareFilter === chip.key} onclick={() => (shareFilter = chip.key)}>{chip.label} <span>{chip.count}</span></button>
        {/each}
      </div>
      <section class="iw__card iw__table" aria-label={t('Guarded folders')}>
        {#each rows as folder (folder.id)}
          <a class="iw__row" href={`/storage-roots?selected=${folder.id}`}>
            <span class="iw__fname"><b>{folder.name}</b><small class="mono">{folder.path}</small></span>
            <span class="iw__muted">{folder.co_guardians.length ? t('with {names}', { names: folder.co_guardians.join(', ') }) : t('no other guardian')}</span>
            <span class="iw__tag" class:is-sole={folder.sole}>{folder.sole ? t('only guardian') : t('shared')}</span>
          </a>
        {:else}
          <EmptyStateInline message={t('Guardian of no folder.')} />
        {/each}
      </section>
    {:else}
      <section class="iw__card" aria-label={t('Activity')}>
        <ActivityTimeline items={activity} emptyLabel={t('No activity for this identity yet.')} />
      </section>
    {/if}
  {/if}

</div>

<style>
  .iw { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .iw__plus { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .iw__seg { display: flex; gap: 2px; padding: 3px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .iw__seg button { padding: 8px 14px; border: 0; border-radius: 10px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-size: var(--b2s-fs-sm); font-weight: 600; cursor: pointer; }
  .iw__seg button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
  .iw__seg button:disabled { cursor: default; }
  .iw__tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .iw__tiles .b2s-stat-tile { text-align: left; border: 1px solid var(--b2s-color-border); font: inherit; color: inherit; }
  .iw__tiles button.b2s-stat-tile { cursor: pointer; }
  .iw__tiles .b2s-stat-tile > span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .iw__tiles .b2s-stat-tile small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .iw__grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 16px; align-items: start; }
  .iw__col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .iw__card { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .iw__card > header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .iw__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .iw__card header small, .iw__muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .iw__muted { margin: 0; }
  .iw__map { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
  .iw__site { display: flex; flex-direction: column; align-items: stretch; gap: 6px; padding: 10px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface); font: inherit; text-align: left; cursor: pointer; }
  .iw__site:hover { border-color: var(--b2s-color-border-strong); background: var(--b2s-color-surface-soft, #f6f7f9); }
  .iw__site-head { display: flex; justify-content: space-between; gap: 6px; font-size: var(--b2s-fs-xs); }
  .iw__site-head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .iw__site-head span { color: var(--b2s-color-text-muted); }
  .iw__cells { display: grid; grid-template-columns: repeat(5, 1fr); gap: 3px; }
  .iw__cell { display: block; height: 7px; border-radius: 2px; background: #3b6fd8; }
  .iw__cell.is-sole { background: #c0392b; }
  .iw__sole { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 12px; background: var(--b2s-color-danger-soft, #fdecea); font-size: var(--b2s-fs-sm); }
  .iw__legend { display: flex; flex-wrap: wrap; gap: 14px; color: var(--b2s-color-text); font-size: var(--b2s-fs-xs); }
  .iw__key { display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 2px; background: #3b6fd8; }
  .iw__key.is-sole { background: #c0392b; }
  .iw__partner { display: flex; align-items: center; gap: 12px; padding: 10px; border: 1px solid var(--b2s-color-border); border-radius: 12px; }
  .iw__partner span:last-child { display: flex; flex-direction: column; }
  .iw__partner b { font-weight: 500; }
  .iw__partner small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .iw__mini { flex: 0 0 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 12px; font-weight: 700; }
  .iw__bar { display: flex; gap: 2px; height: 10px; border-radius: 6px; overflow: hidden; }
  .iw__chipsbar { display: flex; flex-wrap: wrap; gap: 6px; }
  .iw__chipsbar button { padding: 5px 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); background: var(--b2s-color-surface); color: var(--b2s-color-text); font: inherit; font-size: var(--b2s-fs-xs); cursor: pointer; }
  .iw__chipsbar button span { color: var(--b2s-color-text-muted); }
  .iw__chipsbar button.is-on { border-color: var(--b2s-color-text); background: var(--b2s-color-text); color: var(--b2s-color-surface); }
  .iw__chipsbar button.is-on span { color: inherit; opacity: 0.7; }
  .iw__table { padding: 0; gap: 0; overflow: hidden; }
  .iw__row { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) 120px; gap: 12px; align-items: center; padding: 11px 16px; border-top: 1px solid var(--b2s-color-border); color: inherit; text-decoration: none; font-size: var(--b2s-fs-sm); }
  .iw__row:first-child { border-top: 0; }
  .iw__row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .iw__fname { display: flex; flex-direction: column; min-width: 0; }
  .iw__fname b { font-weight: 500; }
  .iw__fname small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); }
  .iw__tag { justify-self: end; padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .iw__tag.is-sole { background: var(--b2s-color-danger-soft, #fdecea); color: var(--b2s-color-danger-strong, #b42318); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
