<script lang="ts">
  import { apiGetList } from '$lib/api/client';
  import { getIdentityOverview, type IdentityOverview } from '$lib/api/identity';
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import EntityTodoCard, { type EntityTodoStep } from '$lib/components/entity/EntityTodoCard.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { timeAgo } from '$lib/utils/format';

  /**
   * One person, as a page: identity card with the role as a switch (undo for a few seconds), « to do », figures,
   * then what they guard (map by share, sole guardian folders, co-guardians), their requests and the activity.
   */
  export let item: Record<string, any>;
  export let canDelete = true;
  /** The signed-in person: no demotion, disabling or deletion of one's own account */
  export let isSelf = false;
  export let busy = false;
  export let onSetRole: (role: 'user' | 'platform_admin') => Promise<boolean> = async () => false;
  export let onToggleActive: () => void = () => {};
  export let onEdit: () => void = () => {};
  export let onDelete: () => void = () => {};

  let data: IdentityOverview | null = null;
  let activity: any[] = [];
  let loadedFor = 0;
  let tab = 'overview';
  let shareFilter = 'all';
  let undo: { role: 'user' | 'platform_admin'; text: string } | null = null;
  let undoTimer: ReturnType<typeof setTimeout> | null = null;

  $: id = Number(item?.id ?? 0);
  $: if (id && id !== loadedFor) load(id);
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

  // Role: held directly (switchable) or through a directory group (shown, not switchable here)
  $: adminVia = (data?.roles ?? []).filter((role) => role.code === 'platform_admin').map((role) => role.via);
  $: isAdmin = adminVia.length > 0;
  $: adminByGroupOnly = isAdmin && !adminVia.includes('direct');
  async function setRole(role: 'user' | 'platform_admin') {
    if (busy || adminByGroupOnly || (role === 'platform_admin') === isAdmin) return;
    const previous: 'user' | 'platform_admin' = isAdmin ? 'platform_admin' : 'user';
    if (!(await onSetRole(role))) return;
    await load(id);
    showUndo(previous, role === 'platform_admin' ? t('{name} is now an administrator.', { name: displayName }) : t('{name} is a user again.', { name: displayName }));
  }
  function showUndo(role: 'user' | 'platform_admin', text: string) {
    if (undoTimer) clearTimeout(undoTimer);
    undo = { role, text };
    undoTimer = setTimeout(() => (undo = null), 8000);
  }
  async function revert() {
    if (!undo) return;
    const role = undo.role;
    undo = null;
    if (await onSetRole(role)) await load(id);
  }

  $: displayName = String(data?.display_name || item?.display_name || item?.username || '—');
  $: initials = displayName.split(/[ .\-_]/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?';
  $: local = String(data?.auth_source ?? item?.auth_source ?? '') === 'local';
  $: hasMail = Boolean(String(data?.email ?? item?.email ?? '').trim());
  $: active = data ? data.is_active : item?.is_active !== false;
  $: guarded = data?.guarded ?? [];
  $: sole = guarded.filter((folder) => folder.sole);
  $: requestsTotal = Object.values(data?.requests ?? {}).reduce((sum, value) => sum + Number(value || 0), 0);

  async function copyDn() {
    try {
      await navigator.clipboard.writeText(String(data?.dn ?? ''));
      toast.success(t('Copied.'));
    } catch {
      toast.error(t('Could not copy.'));
    }
  }

  $: actions = [
    { key: 'edit', label: t('Edit'), icon: 'bi-pencil', variant: 'secondary', onClick: onEdit },
    ...(isSelf ? [] : [
      { key: 'toggle', label: active ? t('Disable') : t('Enable'), icon: active ? 'bi-pause-circle' : 'bi-play-circle', overflow: true, onClick: onToggleActive },
      { key: 'delete', label: t('Delete'), icon: 'bi-trash', variant: 'danger', overflow: true, disabled: !canDelete, onClick: onDelete }
    ])
  ] as EntityActionItem[];

  $: steps = [
    ...(!active && guarded.length ? [{ key: 'off', tone: 'bad' as const, icon: 'bi-pause-circle', title: t('Disabled, but guardian of {count} folder(s)', { count: guarded.length }), detail: t('Its requests wait for the other guardians or an administrator.'), label: t('Enable'), run: onToggleActive }] : []),
    ...(active && guarded.length && !hasMail ? [{ key: 'mail', tone: 'warn' as const, icon: 'bi-envelope-slash', title: t('{count} folder(s) wait for their validations, but there is no e-mail', { count: guarded.length }), detail: local ? t('Neither requests nor reminders reach them. Add an e-mail address.') : t('Neither requests nor reminders reach them. Fill the mail attribute in the directory: it is read again at the next synchronization.'), label: local ? t('Edit') : t('See the folders'), run: local ? onEdit : () => (tab = 'guarded') }] : []),
    ...(sole.length ? [{ key: 'sole', tone: 'info' as const, icon: 'bi-person-exclamation', title: t('Only guardian of {count} folder(s)', { count: sole.length }), detail: t('Without them, only an administrator validates the requests of these folders.'), label: t('See them'), run: () => { tab = 'guarded'; shareFilter = 'sole'; } }] : [])
  ] as EntityTodoStep[];

  // Map of what they guard: one tile per share, one cell per folder (red: only guardian)
  $: shares = [...guarded.reduce((map, folder) => {
    const key = folder.share || '—';
    if (!map.has(key)) map.set(key, { share: key, folders: [] as typeof guarded });
    map.get(key)!.folders.push(folder);
    return map;
  }, new Map<string, { share: string; folders: typeof guarded }>()).values()].sort((a, b) => b.folders.length - a.folders.length || a.share.localeCompare(b.share, 'fr'));
  $: shownShares = shares.slice(0, 20);
  $: shareChips = [
    { key: 'all', label: t('All'), count: guarded.length },
    ...(sole.length ? [{ key: 'sole', label: t('Only guardian'), count: sole.length }] : []),
    ...shares.slice(0, 8).map((share) => ({ key: `share:${share.share}`, label: share.share, count: share.folders.length }))
  ];
  $: rows = guarded.filter((folder) => shareFilter === 'all' || (shareFilter === 'sole' ? folder.sole : `share:${folder.share}` === shareFilter));
  const REQUEST_TONES: Record<string, string> = { approved: '#2f9e5b', applied: '#2f9e5b', active: '#2f9e5b', pending: '#3b6fd8', revoked: '#8a93a3', rejected: '#c0392b', cancelled: '#cdd2db', expired: '#b9c0cc' };
  $: requestParts = Object.entries(data?.requests ?? {}).filter(([, count]) => Number(count) > 0).sort((a, b) => Number(b[1]) - Number(a[1]));
  const REQUEST_LABEL = (): Record<string, string> => ({ approved: t('approved'), applied: t('applied'), active: t('active'), pending: t('pending'), revoked: t('revoked'), rejected: t('rejected'), cancelled: t('cancelled'), expired: t('expired') });

  $: tabs = [
    { key: 'overview', label: t('Overview') },
    { key: 'guarded', label: t('Guarded folders'), count: guarded.length || null },
    { key: 'activity', label: t('Activity'), count: activity.length || null }
  ];
</script>

<div class="iw">
  <header class="iw__hero">
    <span class="iw__avatar" class:is-ring={active && !local} class:is-off={!active} title={active ? (local ? t('Local account') : t('Synchronized with the directory')) : t('Disabled')}>{initials}</span>
    <div class="iw__main">
      <nav class="iw__crumbs" aria-label={t('Location')}>{t('Identities')} <i class="bi bi-chevron-right" aria-hidden="true"></i> {data?.source_name ?? item?.source_name ?? ''}</nav>
      <div class="iw__title">
        <h1>{displayName}</h1>
        <span class="iw__pill" class:is-off={!active}><span aria-hidden="true"></span>{active ? t('Active') : t('Disabled')}</span>
        {#if data?.updated_at}<small>{t('updated {when}', { when: timeAgo(data.updated_at) })}</small>{/if}
      </div>
      <div class="iw__chips">
        {#if data?.dn}<span class="iw__chip mono">{data.dn}<button type="button" on:click={copyDn}>{t('Copy')}</button></span>{/if}
        {#if !data?.dn && (data?.username || item?.username)}<span class="iw__chip mono">{data?.username ?? item?.username}</span>{/if}
        {#if hasMail}<span class="iw__chip">{data?.email ?? item?.email}</span>{:else}<span class="iw__chip is-warn">{t('No e-mail address')}</span>{/if}
        {#if adminByGroupOnly}<span class="iw__chip"><i class="bi bi-people" aria-hidden="true"></i>{t('Administrator through a directory group')}</span>{/if}
      </div>
    </div>
    <div class="iw__side">
      <div class="iw__seg" role="radiogroup" aria-label={t('Role in BornToShare')}>
        <button type="button" role="radio" aria-checked={!isAdmin} class:is-on={!isAdmin} disabled={busy || adminByGroupOnly || !data || (isSelf && isAdmin)} title={isSelf && isAdmin ? t('You cannot demote your own account.') : undefined} on:click={() => setRole('user')}>{t('User')}</button>
        <button type="button" role="radio" aria-checked={isAdmin} class:is-on={isAdmin} disabled={busy || adminByGroupOnly || !data} on:click={() => setRole('platform_admin')}>{t('Administrator')}</button>
      </div>
      {#if guarded.length}<small>{t('+ guardian of {count} folder(s)', { count: guarded.length })}</small>{/if}
      <EntityActionGroup {actions} ariaLabel={t('Identity actions')} />
    </div>
  </header>

  {#if !data}
    <LoadingState block skeleton="detail" />
  {:else}
    <div class="b2s-stat-tiles iw__tiles">
      <div class="b2s-stat-tile"><span>{t('Role')}</span><b>{isAdmin ? t('Administrator') : guarded.length ? t('Guardian') : t('User')}</b><small>{isAdmin && guarded.length ? t('and guardian') : guarded.length ? t('and user') : ''}</small></div>
      <button type="button" class="b2s-stat-tile" on:click={() => (tab = 'guarded')}><span>{t('Guarded folders')}</span><b>{guarded.length}</b><small>{sole.length ? t('{count} as only guardian', { count: sole.length }) : t('always with another guardian')}</small></button>
      <div class="b2s-stat-tile"><span>{t('Accesses in progress')}</span><b>{data.active_accesses}</b><small>{data.active_accesses ? '' : t('no folder open for them')}</small></div>
      <div class="b2s-stat-tile"><span>{t('Requests')}</span><b>{requestsTotal}</b><small>{requestParts.map(([status, count]) => `${count} ${REQUEST_LABEL()[status] ?? status}`).join(' · ')}</small></div>
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
                <button type="button" class="iw__site" title={t('{share}: {count} folder(s)', { share: share.share, count: share.folders.length })} on:click={() => { tab = 'guarded'; shareFilter = `share:${share.share}`; }}>
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
          <button type="button" class:is-on={shareFilter === chip.key} on:click={() => (shareFilter = chip.key)}>{chip.label} <span>{chip.count}</span></button>
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

  {#if undo}
    <div class="iw__undo" role="status">
      <span>{undo.text}</span>
      <button type="button" on:click={revert}>{t('Undo')}</button>
    </div>
  {/if}
</div>

<style>
  .iw { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .iw__hero { display: flex; gap: 20px; align-items: flex-start; padding: 22px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm, 0 1px 2px rgba(14, 18, 24, 0.04)); }
  .iw__avatar { flex: 0 0 60px; height: 60px; display: grid; place-items: center; border-radius: 50%; background: linear-gradient(135deg, var(--b2s-color-info-soft), #c9d9fb); color: var(--b2s-color-info-strong); font-size: 20px; font-weight: 700; }
  .iw__avatar.is-off { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .iw__avatar.is-ring { animation: iw-ring 2.4s ease-in-out infinite; }
  @keyframes iw-ring { 0%, 100% { box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 5px #2f9e5b; } 50% { box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 8px rgba(47, 158, 91, 0.25); } }
  @media (prefers-reduced-motion: reduce) { .iw__avatar.is-ring { animation: none; box-shadow: 0 0 0 3px var(--b2s-color-surface), 0 0 0 5px #2f9e5b; } }
  .iw__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 10px; }
  .iw__crumbs { display: flex; align-items: center; gap: 6px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .iw__crumbs i { font-size: 10px; }
  .iw__title { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .iw__title h1 { margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
  .iw__title small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .iw__pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-success-soft, #ddf5e9); color: var(--b2s-color-success-strong, #157a3c); font-size: var(--b2s-fs-xs); font-weight: 500; }
  .iw__pill span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .iw__pill.is-off { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .iw__chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .iw__chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; padding: 5px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-sm, 8px); background: var(--b2s-color-surface-soft, #f5f7fa); color: var(--b2s-color-text); font-size: var(--b2s-fs-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .iw__chip button { padding: 2px 6px; border: 0; border-radius: 6px; background: var(--b2s-color-surface); font: inherit; font-family: var(--b2s-font-sans); cursor: pointer; }
  .iw__chip.is-warn { border-color: var(--b2s-color-warning-border, #f3d9a8); background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); }
  .iw__side { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex: none; }
  .iw__side small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
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
  .iw__undo { position: fixed; right: 28px; bottom: 24px; z-index: 40; display: flex; align-items: center; gap: 14px; padding: 12px 14px 12px 16px; border-radius: 12px; background: #0e1218; color: #ffffff; font-size: var(--b2s-fs-sm); box-shadow: 0 12px 30px rgba(14, 18, 24, 0.25); animation: iw-rise 0.25s ease-out; }
  .iw__undo button { border: 0; background: transparent; color: #b6f24a; font: inherit; font-weight: 600; cursor: pointer; }
  @keyframes iw-rise { from { transform: translateY(12px); opacity: 0; } to { transform: none; opacity: 1; } }
</style>
